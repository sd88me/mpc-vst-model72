// Model-72 for MPC / Force: the native front end (framework/mpc_plugin.h) around the unchanged CA-72 engine (engine/ca72-mpc, Rust,
// linked as a static library: ca72_create / _midi / _set_param / _get_param / _render / _destroy).
//
// Signal flow: host MIDI (sample accurate) -> engine midi -> engine render (int16 stereo at 44.1 kHz) -> float outputs. The MPC runs
// at 44.1 kHz; at any other host rate a linear resampler sits between the engine and the outputs (MIDI then lands per engine block).
//
// Parameters: the released 1.0.1 build's 72 in the same order (vst/params.json -> tools/gen_sdk_params.py -> params_gen.h), then the
// SDK version's own, appended (vst/params.lock).
//   * value params: a host change goes to the engine as its set_param string in engine units (options as indices). Whole numbers and
//     options settle toward the direction of a Q-Link move, so a small turn moves one step (the 1.x wrapper's rule).
//   * readouts (kPushed): auto_db (AUTO GAIN's correction, text; the value is a counter bumped when the text changes, since the host only
//     re-reads text when the value moves) and dot_1..10 (the STEREO field) are the engine's: read back by the worker and told to the host.
//   * programs: the PRESET menu lists the 19 factory presets (as 1.0.1 did), then kFavSlots user presets ("U01 <name>").
//   * user presets (kLocal): +PRESET opens the drawn keyboard (kb_open = 1) with the current program's name; SAVE stores the sound as it
//     was when +PRESET was pressed (the engine state, with edits) under the typed name in the first free slot, -PRESET deletes the picked
//     one. Kept in <plugin folder>/model72-presets.dat (.tmp + rename), shared by every project. A key's repeat within 250 ms is ignored
//     (the MPC can report one tap on a drawn key twice).
// Parameter 0 is QUALITY (HI builds the circuit filter). The host nudges parameter 0 on every prepare: a change applies only after it
// has held for ~40 ms.
// State: the engine's own "state" text ("quality=0;mode=1;...") is the truth; it travels as the MPC chunk's extra state, and nothing is
// written to the engine while the MPC chunk restores parameter values. A project saved by the 1.0.x wrapper build stored only that text
// (with its NUL) as its chunk: it is still read (effSetChunk is wrapped below).

#include "mpc_plugin.h"

#include "params_gen.h"
#include "presets_gen.h"

#include <pthread.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

extern "C" {
void* ca72_create(void);
void ca72_destroy(void* e);
void ca72_midi(void* e, const uint8_t* m, int len);
void ca72_set_param(void* e, const char* k, const char* v);
int ca72_get_param(void* e, const char* k, char* buf, int len);
void ca72_render(void* e, int16_t* out, int frames);
}

#ifndef M72_NAME
#define M72_NAME "Model-72"
#endif
#ifndef M72_UID
#define M72_UID 'M', '0', '7', '2'
#endif
#define M72_FOURCC(...) MPC_FOURCC(__VA_ARGS__)   // expands M72_UID before MPC_FOURCC counts its arguments
#ifndef M72_VERSION
#define M72_VERSION 2000
#endif

namespace {

const int kChunk = 128;
const int kStateMax = 4096;
const double kEngineRate = 44100.0;
// QUALITY for a new instance: HI on Gen2 (arm64, room for the circuit filter), LO on the Force / Gen1 (arm32: HI costs 30-55 % of a core).
#if defined(__aarch64__)
const int kDefaultQuality = 1;
#else
const int kDefaultQuality = 0;
#endif

// A preset's sound without its QUALITY: LO / HI is the device's choice, not the sound's (a project keeps its own).
std::string withoutQuality(const std::string& st)
{
    std::string out;
    size_t a = 0;
    while (a < st.size())
    {
        size_t b = st.find(';', a);
        if (b == std::string::npos) b = st.size();
        if (st.compare(a, 8, "quality=") != 0) { if (!out.empty()) out += ';'; out.append(st, a, b - a); }
        a = b + 1;
    }
    return out;
}

mpc::PluginInfo makeInfo()
{
    mpc::PluginInfo i;
    i.name = M72_NAME;
    i.vendor = "sd88me";
    i.uniqueId = M72_FOURCC(M72_UID);
    i.version = M72_VERSION;
    i.isInstrument = true;
    i.numInputs = 0;
    i.numOutputs = 2;
    return i;
}

long long nowMs()
{
    return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

uint32_t fnv(const char* s)
{
    uint32_t h = 2166136261u;
    for (; *s; ++s) h = (h ^ (unsigned char)*s) * 16777619u;
    return h;
}

// The engine's state text: "key=value;..." over its keys, starting with the first one (quality).
bool isState(const std::string& s) { return s.compare(0, 8, "quality=") == 0; }

thread_local int t_pushing = -1;   // the parameter the worker is telling the host about right now (its echo is ignored)

} // namespace

class Model72Plugin : public mpc::Plugin
{
public:
    Model72Plugin() : mpc::Plugin(makeInfo())
    {
        for (int i = 0; i < kNumParams; ++i)
        {
            const PSpec& s = g_pspecs[i];
            mpc::Param p = (s.flags & kChoice) ? mpc::choiceParam(s.key, s.name, std::vector<std::string>(s.choices, s.choices + s.nchoices), (int)s.def)
                         : (s.flags & kFloat)  ? mpc::floatParam(s.key, s.name, s.min, s.max, s.def, "", 2)
                                               : mpc::intParam(s.key, s.name, (int)s.min, (int)s.max, (int)s.def);
            p.automatable = !(s.flags & kNoAuto);
            if (i == 0) p.def = (float)kDefaultQuality;
            addParam(p);
        }
        const size_t n = (size_t)kNumParams;
        held_ = new std::atomic<bool>[n];
        release_ = new std::atomic<bool>[n];
        hostAt_ = new std::atomic<long long>[n];
        told_ = new std::atomic<float>[n];
        for (size_t i = 0; i < n; ++i) { held_[i].store(false); release_[i].store(false); hostAt_[i].store(0); told_[i].store(-1.0e9f); }
        lastPos_.assign(n, -1.0f);
        lastFire_.assign(n, 0);

        pthread_mutexattr_t ma;   // recursive + priority-inheriting: audio waiting on a short worker call lifts it
        pthread_mutexattr_init(&ma);
        pthread_mutexattr_settype(&ma, PTHREAD_MUTEX_RECURSIVE);
        pthread_mutexattr_setprotocol(&ma, PTHREAD_PRIO_INHERIT);
        pthread_mutex_init(&lock_, &ma);
        pthread_mutexattr_destroy(&ma);

        inst_ = ca72_create();
        if (inst_ && kDefaultQuality) ca72_set_param(inst_, "quality", "1");   // Gen2 (arm64) starts in HI
        for (int i = 0; i < kFactory; ++i) addProgram(g_factory[i].name, {});
        for (int i = 0; i < kFavSlots; ++i) addProgram("", {});
        // (Not mpc::contentPath(): a function-local static std::string segfaults at dlclose.)
        favFile_ = mpc::detail::computePluginFolder() + "/model72-presets.dat";
        loadFavs();
        worker_ = std::thread(&Model72Plugin::workerMain, this);
    }

    ~Model72Plugin() override
    {
        quit_.store(true);
        if (worker_.joinable()) worker_.join();
        if (inst_) ca72_destroy(inst_);
        pthread_mutex_destroy(&lock_);
        delete[] held_;
        delete[] release_;
        delete[] hostAt_;
        delete[] told_;
    }

    void prepare(double sampleRate, int) override
    {
        step_ = sampleRate > 0 ? kEngineRate / sampleRate : 1.0;
        resampling_ = std::fabs(step_ - 1.0) > 1e-9;
        rsPos_ = 0.0;
        rsHave_ = 0;
    }

    // ---- audio ----------------------------------------------------------------------------------------------------------------
    void process(mpc::ProcessContext& ctx) override
    {
        if (!inst_) return;
        float* L = ctx.outputs[0];
        float* R = ctx.numOutputs > 1 ? ctx.outputs[1] : nullptr;
        if (resampling_) { processResampled(ctx, L, R); return; }
        int frame = 0, mi = 0;
        while (frame < ctx.numFrames)
        {
            while (mi < ctx.numMidiEvents && ctx.midi[mi].sampleOffset <= frame) sendMidi(ctx.midi[mi++]);
            int end = ctx.numFrames;
            if (mi < ctx.numMidiEvents) end = std::min(std::max(ctx.midi[mi].sampleOffset, frame + 1), ctx.numFrames);
            while (frame < end)
            {
                const int n = std::min(end - frame, kChunk);
                { Lock l(this); ca72_render(inst_, pcm_, n); }
                for (int i = 0; i < n; ++i)
                {
                    L[frame + i] = pcm_[2 * i] * (1.0f / 32768.0f);
                    if (R) R[frame + i] = pcm_[2 * i + 1] * (1.0f / 32768.0f);
                }
                frame += n;
            }
        }
    }

    // ---- parameters -----------------------------------------------------------------------------------------------------------
    void parameterChanged(int index, float plain) override
    {
        if (index < 0 || index >= kNumParams || !inst_) return;
        if (t_pushing == index) return;          // the host echoing what the worker just told it
        const PSpec& s = g_pspecs[index];
        if (index == kPitchWheel) { pitchWheel(plain); return; }
        if (s.flags & kLocal) { localChanged(index, plain); return; }
        if (s.flags & kReadOnly) return;         // the engine's readouts
        hostAt_[index].store(nowMs());
        if (loading_.load()) return;             // an MPC chunk is restoring values: the engine state follows as extra state
        char buf[32];
        float v = plain;
        if (s.flags & kFloat)
        {
            v = std::min(std::max(v, s.min), s.max);
            std::snprintf(buf, sizeof buf, "%.6g", v);
        }
        else   // whole numbers and options: settle toward the move, then send
        {
            const float span = s.max - s.min;
            const float pos = getNormalised(index) * span;
            const float cur = told_[index] > -1.0e8f ? told_[index] - s.min : pos;
            float steps = settle(pos, cur, lastPos_[(size_t)index]);
            lastPos_[(size_t)index] = pos;
            steps = std::min(std::max(steps, 0.0f), span);
            v = s.min + steps;
            if (std::fabs(pos - steps) > 0.001f) settled_.store(true);   // the worker tells the host where it landed
            std::snprintf(buf, sizeof buf, "%d", (int)std::lround(v));
        }
        if (index == 0)   // QUALITY, debounced (see the header comment)
        {
            pend0Value_.store(v);
            pend0At_.store(nowMs());
            return;
        }
        told_[index] = v;
        engineSet(s.key, buf);
    }

    bool formatValue(int index, float plain, std::string& out) override
    {
        if (index < 0 || index >= kNumParams) return false;
        const PSpec& s = g_pspecs[index];
        char buf[128];
        if (index == kFavName) { std::lock_guard<std::mutex> g(favMu_); out = kbName_ + "_"; return true; }
        if (index == kAutoDb) { out = engineGet("auto_db", buf, sizeof buf) ? std::string(buf) + " dB" : ""; return true; }
        if (s.flags & kMomentary) { out = ""; return true; }
        if (s.flags & kFloat) { std::snprintf(buf, sizeof buf, "%.2f", plain); out = buf; return true; }
        return false;
    }

    // ---- state ----------------------------------------------------------------------------------------------------------------
    void saveExtraState(std::vector<uint8_t>& out) override
    {
        const std::string s = engineState();
        out.assign(s.begin(), s.end());
    }

    void loadExtraState(const uint8_t* data, size_t size) override
    {
        if (!data || !size) return;
        projectLoaded();
        applyState(std::string(reinterpret_cast<const char*>(data), strnlen(reinterpret_cast<const char*>(data), size)));
    }

    // A project saved by the 1.0.x wrapper build: its chunk is the engine's state text, NUL-terminated. Called from the wrapped effSetChunk.
    bool loadLegacy(const char* data, size_t size)
    {
        if (!data || !size) return false;
        const std::string s(data, strnlen(data, size));
        if (!isState(s)) return false;
        projectLoaded();
        applyState(s);
        return true;
    }

    // The MPC picked a program in its PRESET menu (the wrapped effSetProgram; the framework has already stored the pick).
    void programPicked(int prog)
    {
        if (prog < 0 || prog >= kFactory + kFavSlots || nowMs() < ignoreProgUntil_.load()) return;
        if (prog < kFactory) { applyState(g_factory[prog].state, false); return; }   // (the factory table has no quality)
        std::string st;
        { std::lock_guard<std::mutex> g(favMu_); if (favs_[(size_t)(prog - kFactory)].used) st = favs_[(size_t)(prog - kFactory)].state; }
        if (!st.empty()) applyState(withoutQuality(st), false);
    }

    std::atomic<bool> loading_{false};   // set around an MPC chunk load (wrapped effSetChunk)
    void requestResync() { resync_.store(true); }

private:
    struct Lock
    {
        explicit Lock(Model72Plugin* p) : p_(p) { pthread_mutex_lock(&p_->lock_); }
        ~Lock() { pthread_mutex_unlock(&p_->lock_); }
        Model72Plugin* p_;
    };

    // The OUTPUT tab's pitch wheel (-1..1): a MIDI pitch bend to the engine (BEND RANGE applies), as a wheel on a keyboard would send.
    void pitchWheel(float v)
    {
        v = std::min(std::max(v, -1.0f), 1.0f);
        const int b = std::min(16383, std::max(0, 8192 + (int)std::lround(v * (v < 0 ? 8192.0f : 8191.0f))));
        const uint8_t m[3] = {0xE0, (uint8_t)(b & 0x7F), (uint8_t)(b >> 7)};
        Lock l(this);
        ca72_midi(inst_, m, 3);
    }

    void sendMidi(const mpc::MidiEvent& e)
    {
        Lock l(this);
        ca72_midi(inst_, e.data, e.size);
    }

    // A host that is not at 44.1 kHz: the engine renders at its own rate into rs_, read out with linear interpolation.
    void processResampled(mpc::ProcessContext& ctx, float* L, float* R)
    {
        for (int i = 0; i < ctx.numMidiEvents; ++i) sendMidi(ctx.midi[i]);
        for (int f = 0; f < ctx.numFrames; ++f)
        {
            while (rsPos_ + 1.0 >= (double)rsHave_)   // need frames ipos and ipos + 1
            {
                if (rsHave_ >= 2) { rs_[0] = rs_[2 * (rsHave_ - 1)]; rs_[1] = rs_[2 * (rsHave_ - 1) + 1]; rsPos_ -= (double)(rsHave_ - 1); rsHave_ = 1; }
                { Lock l(this); ca72_render(inst_, pcm_, kChunk); }
                for (int i = 0; i < kChunk; ++i) { rs_[2 * (rsHave_ + i)] = pcm_[2 * i]; rs_[2 * (rsHave_ + i) + 1] = pcm_[2 * i + 1]; }
                rsHave_ += kChunk;
            }
            const int i0 = (int)rsPos_;
            const float t = (float)(rsPos_ - i0);
            L[f] = (rs_[2 * i0] + (rs_[2 * i0 + 2] - rs_[2 * i0]) * t) * (1.0f / 32768.0f);
            if (R) R[f] = (rs_[2 * i0 + 1] + (rs_[2 * i0 + 3] - rs_[2 * i0 + 1]) * t) * (1.0f / 32768.0f);
            rsPos_ += step_;
        }
    }

    void engineSet(const char* key, const char* val)
    {
        Lock l(this);
        ca72_set_param(inst_, key, val);
    }

    bool engineGet(const char* key, char* buf, int n)
    {
        int r;
        { Lock l(this); r = ca72_get_param(inst_, key, buf, n); }
        if (r <= 0) { buf[0] = 0; return false; }
        buf[r < n ? r : n - 1] = 0;
        return true;
    }

    std::string engineState()
    {
        std::vector<char> buf((size_t)kStateMax);
        return inst_ && engineGet("state", buf.data(), kStateMax) ? std::string(buf.data()) : std::string();
    }

    // A whole sound at once (project, factory preset, user preset): the engine takes it, then every value is read back to the host.
    void applyState(const std::string& s, bool check = true)
    {
        if (inst_ && (!check || isState(s))) engineSet("state", s.c_str());
        pend0At_.store(0);   // a QUALITY move still pending is overridden by the new sound
        resync_.store(true);
    }

    void projectLoaded()
    {
        ignoreProgUntil_.store(nowMs() + 2000);   // the host re-picks the saved program after a project load: the project's sound wins
        kbOpen_.store(false);
        kbDirty_.store(true);   // a project saved with the keyboard open restored kb_open = 1: push it closed
    }

    // Set a parameter's value without calling parameterChanged (so it is not written back to the engine).
    void store(int i, float plain) { values_[(size_t)i]->store(param(i).toNormalised(plain), std::memory_order_relaxed); }

    // Where a whole-number / option param lands, in steps from its minimum (the 1.x wrapper's rule): a value on a step is a click,
    // a preset or automation; between steps it is a Q-Link / wheel / drag move, rounded toward the way it moves.
    static float settle(float pos, float cur, float last)
    {
        if (std::fabs(pos - std::round(pos)) <= 0.001f) return std::round(pos);
        const float dir = (last >= 0 && std::fabs(pos - last) < 0.5f) ? pos - last : pos - cur;
        if (dir == 0) return std::round(cur);
        return dir > 0 ? std::ceil(pos - 0.001f) : std::floor(pos + 0.001f);
    }

    // ---- worker: debounced QUALITY, momentary releases, readouts, read-back after a whole-sound change ---------------------------
    void pushValue(int i, float plain)
    {
        told_[i] = plain;
        store(i, plain);
        t_pushing = i;
        notifyHostParameterChanged(i);
        t_pushing = -1;
    }

    void workerMain()
    {
        while (!quit_.load())
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
            tickOnce(false);
        }
    }

    // One worker pass. force = the offline test: apply a pending QUALITY now and read back everything.
    void tickOnce(bool force)
    {
        if (!inst_) return;
        const long long now = nowMs();
        ++tick_;
        char buf[128];
        const long long p0 = pend0At_.load();
        if (p0 && (force || now - p0 >= 40))
        {
            pend0At_.store(0);
            std::snprintf(buf, sizeof buf, "%d", (int)std::lround(pend0Value_.load()));
            engineSet(g_pspecs[0].key, buf);
            told_[0] = pend0Value_.load();
            settled_.store(true);
        }
        for (int i = 0; i < kNumParams; ++i)
            if (release_[i].exchange(false)) { held_[i].store(false); pushValue(i, 0.0f); }

        // after a whole-sound change, or where a stepped value settled: read the engine's values back and tell the host what moved
        const bool full = resync_.exchange(false) || force;
        const bool settled = settled_.exchange(false);
        int changed = 0;
        if (full || settled)
            for (int i = 0; i < kNumEngineParams; ++i)
            {
                const PSpec& s = g_pspecs[i];
                if (s.flags & kReadOnly) continue;
                if (i == 0 && pend0At_.load()) continue;
                const long long at = hostAt_[i].load();
                if (!full && !force && now - at < 300) { settled_.store(true); continue; }   // still being moved: later
                if (!engineGet(s.key, buf, sizeof buf)) continue;
                float v = std::min(std::max((float)std::atof(buf), s.min), s.max);
                if (hostAt_[i].load() != at) { settled_.store(true); continue; }   // a host write in between: look again next pass
                const float hostV = s.min + getNormalised(i) * (s.max - s.min);
                if (full ? std::fabs(v - hostV) > 1e-4f || std::fabs(v - told_[i]) > 1e-4f : std::fabs(v - hostV) > 1e-4f)
                {
                    pushValue(i, v);
                    ++changed;
                }
                else told_[i] = v;
            }

        // the STEREO field: the engine bumps display_rev when its dots move
        if (engineGet("display_rev", buf, sizeof buf))
        {
            const uint32_t r = fnv(buf) | 1u;
            if (r != lastRev_ || full)
            {
                lastRev_ = r;
                for (int d = 0; d < kDots; ++d)
                {
                    char k[24];
                    std::snprintf(k, sizeof k, "dot_%d", d + 1);
                    if (!engineGet(k, buf, sizeof buf)) continue;
                    const float v = std::min(std::max((float)std::atof(buf), 0.0f), 1.0f);
                    if (std::fabs(v - told_[kDot1 + d]) > 1e-4f) pushValue(kDot1 + d, v);
                }
            }
        }
        // AUTO GAIN's readout: every 100 ms; a changed text bumps the counter
        if (force || full || tick_ % 10 == 0)
        {
            const uint32_t h = engineGet("auto_db", buf, sizeof buf) ? fnv(buf) | 1u : 1u;
            if (h != autoDbHash_)
            {
                autoDbHash_ = h;
                counter_ = (counter_ + 1) % 1024;
                pushValue(kAutoDb, (float)counter_);
                wantDisplay_ = true;
            }
        }
        if (favDirty_.exchange(false)) { saveFavs(); wantDisplay_ = true; }   // new names in the PRESET menu
        if (kbDirty_.exchange(false))   // the keyboard opened or closed, or the typed name changed
        {
            pushValue(kKbOpen, kbOpen_.load() ? 1.0f : 0.0f);
            nameCounter_ = (nameCounter_ + 1) % 1024;
            pushValue(kFavName, (float)nameCounter_);
            wantDisplay_ = true;
        }
        // Many values at once or new text: one display update, at most every 100 ms. Never periodically: it re-lists programs and
        // closes the PRESET menu.
        if (changed > 8) wantDisplay_ = true;
        if (wantDisplay_ && (force || now - lastDisplay_ >= 100))
        {
            wantDisplay_ = false;
            lastDisplay_ = now;
            requestDisplayUpdate();
        }
    }

    // ---- user presets (kLocal) --------------------------------------------------------------------------------------------------
    struct Fav { bool used = false; std::string name, state; };

    // "M72P", slot count, then per slot: used (1 byte), name length + name, state length + state (u32 little endian lengths)
    void loadFavs()
    {
        std::lock_guard<std::mutex> g(favMu_);
        favs_.assign(kFavSlots, Fav());
        std::ifstream f(favFile_, std::ios::binary);
        char magic[4] = {};
        uint32_t n = 0;
        if (f.read(magic, 4) && !std::memcmp(magic, "M72P", 4) && f.read(reinterpret_cast<char*>(&n), 4))
            for (uint32_t i = 0; i < n && i < (uint32_t)kFavSlots; ++i)
            {
                char used = 0;
                uint32_t ln = 0, ls = 0;
                if (!f.read(&used, 1) || !f.read(reinterpret_cast<char*>(&ln), 4) || ln > 256) break;
                std::string name(ln, '\0');
                if (ln && !f.read(&name[0], ln)) break;
                if (!f.read(reinterpret_cast<char*>(&ls), 4) || ls > (uint32_t)kStateMax) break;
                std::string st(ls, '\0');
                if (ls && !f.read(&st[0], ls)) break;
                favs_[i].used = used != 0 && isState(st);
                favs_[i].name = name;
                favs_[i].state = st;
            }
        for (int i = 0; i < kFavSlots; ++i) nameProgram(i);
    }

    void saveFavs()   // worker thread: a snapshot under the lock, then the file (.tmp + rename)
    {
        std::vector<Fav> snap;
        { std::lock_guard<std::mutex> g(favMu_); snap = favs_; }
        const std::string tmp = favFile_ + ".tmp";
        {
            std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
            if (!f) return;
            const uint32_t n = (uint32_t)snap.size();
            f.write("M72P", 4);
            f.write(reinterpret_cast<const char*>(&n), 4);
            for (const Fav& v : snap)
            {
                const char used = v.used ? 1 : 0;
                const uint32_t ln = (uint32_t)v.name.size(), ls = (uint32_t)v.state.size();
                f.write(&used, 1);
                f.write(reinterpret_cast<const char*>(&ln), 4);
                f.write(v.name.data(), ln);
                f.write(reinterpret_cast<const char*>(&ls), 4);
                f.write(v.state.data(), ls);
            }
        }
        std::rename(tmp.c_str(), favFile_.c_str());
    }

    void nameProgram(int i)   // favMu_ held
    {
        char b[16];
        std::snprintf(b, sizeof b, "U%02d ", i + 1);
        programs_[(size_t)(kFactory + i)].name = b + (favs_[(size_t)i].used ? favs_[(size_t)i].name : std::string("--"));
    }

    std::string currentName()
    {
        const int p = currentProgram();
        if (p >= 0 && p < kFactory) return g_factory[p].name;
        std::lock_guard<std::mutex> g(favMu_);
        if (p >= kFactory && p < kFactory + kFavSlots && favs_[(size_t)(p - kFactory)].used) return favs_[(size_t)(p - kFactory)].name;
        return "";
    }

    void typeKey(int k)   // favMu_ held; k = 0 .. kKbCount - 1
    {
        const int nchars = (int)sizeof kKbChars - 1;
        if (k <= nchars)   // a character or space
        {
            if ((int)kbName_.size() >= kFavNameMax) return;
            char c = k < nchars ? kKbChars[k] : ' ';
            const bool cap = kbName_.empty() || kbName_.back() == ' ';
            if (c >= 'A' && c <= 'Z')
            {
                if (cap == kbShift_) c = (char)(c - 'A' + 'a');   // capital at the start and after a space; SHIFT flips the next letter
                kbShift_ = false;
            }
            kbName_ += c;
        }
        else if (k == nchars + 1) { if (!kbName_.empty()) kbName_.pop_back(); }
        else if (k == nchars + 2) kbShift_ = !kbShift_;
    }

    void localChanged(int index, float plain)
    {
        if (!(g_pspecs[index].flags & kMomentary)) return;   // kb_open / fav_name: set by the plugin only
        if (plain < 0.5f) { held_[index].store(false); return; }
        if (held_[index].exchange(true)) return;
        release_[index].store(true);   // a momentary: back to 0 on the next worker pass
        const long long now = nowMs();
        if (now - lastFire_[(size_t)index] < 250) return;   // the second report of one tap
        lastFire_[(size_t)index] = now;
        if (index >= kKbFirst && index < kKbFirst + kKbCount)
        {
            if (!kbOpen_.load()) return;
            const int k = index - kKbFirst, nchars = (int)sizeof kKbChars - 1;
            if (k == nchars + 3) { if (kbOpen_.exchange(false)) kbDirty_.store(true); return; }   // CANCEL
            if (k == nchars + 4) { saveTyped(); return; }                                          // SAVE
            { std::lock_guard<std::mutex> g(favMu_); typeKey(k); }
            kbDirty_.store(true);
            return;
        }
        if (index == kFavAdd)   // open the keyboard on the current program's name; the sound is taken now
        {
            const std::string st = engineState();
            if (!isState(st)) return;
            std::string name = currentName();
            if (name.size() > (size_t)kFavNameMax) name.resize((size_t)kFavNameMax);
            {
                std::lock_guard<std::mutex> g(favMu_);
                kbState_ = st;
                kbName_ = name;
                kbShift_ = false;
            }
            kbOpen_.store(true);
            kbDirty_.store(true);
            return;
        }
        if (index == kFavDel)   // the user preset that is picked now
        {
            const int slot = currentProgram() - kFactory;
            if (slot < 0 || slot >= kFavSlots) return;
            bool had;
            {
                std::lock_guard<std::mutex> g(favMu_);
                had = favs_[(size_t)slot].used;
                if (had) { favs_[(size_t)slot] = Fav(); nameProgram(slot); }
            }
            if (had) favDirty_.store(true);
        }
    }

    void saveTyped()
    {
        Fav v;
        {
            std::lock_guard<std::mutex> g(favMu_);
            v.state = kbState_;
            v.name = kbName_;
        }
        while (!v.name.empty() && v.name.back() == ' ') v.name.pop_back();
        if (v.name.empty()) v.name = "User";
        if (kbOpen_.exchange(false)) kbDirty_.store(true);
        if (!isState(v.state)) return;
        v.used = true;
        int slot = -1;
        {
            std::lock_guard<std::mutex> g(favMu_);
            for (int i = 0; i < kFavSlots && slot < 0; ++i) if (!favs_[(size_t)i].used) slot = i;
            if (slot >= 0) { favs_[(size_t)slot] = v; nameProgram(slot); }
        }
        if (slot >= 0)
        {
            currentProgram_ = kFactory + slot;   // the new preset is now the picked one
            favDirty_.store(true);
        }
    }

public:
#ifdef M72_TEST
    void dbgTick() { tickOnce(true); }
    std::string dbgEngine(const char* key)
    {
        char b[kStateMax];
        return engineGet(key, b, sizeof b) ? std::string(b) : std::string();
    }
    void dbgNoIgnore() { ignoreProgUntil_.store(0); }
    void dbgNoRepeatGuard() { std::fill(lastFire_.begin(), lastFire_.end(), 0LL); }
    int dbgFavCount()
    {
        std::lock_guard<std::mutex> g(favMu_);
        int n = 0;
        for (const Fav& v : favs_) n += v.used ? 1 : 0;
        return n;
    }
#endif

private:
    void* inst_ = nullptr;
    std::string favFile_;
    std::mutex favMu_;
    std::vector<Fav> favs_;
    std::atomic<bool> favDirty_{false};
    std::atomic<bool> kbOpen_{false}, kbDirty_{false};
    std::string kbName_, kbState_;     // favMu_: the name being typed, the sound +PRESET took
    bool kbShift_ = false;
    std::vector<long long> lastFire_;  // per local momentary: when it last fired
    pthread_mutex_t lock_;             // one engine call at a time
    std::thread worker_;
    std::atomic<bool> quit_{false};
    std::atomic<bool> resync_{true};
    std::atomic<bool> settled_{false};
    std::atomic<long long> pend0At_{0};
    std::atomic<float> pend0Value_{0.0f};
    std::atomic<bool>* held_ = nullptr;
    std::atomic<bool>* release_ = nullptr;
    std::atomic<long long>* hostAt_ = nullptr; // when the host last moved it (ms), per parameter
    std::atomic<float>* told_ = nullptr;       // the value the host was last told (or sent), per parameter
    std::vector<float> lastPos_;               // the host's last position, for settle()
    std::atomic<long long> ignoreProgUntil_{0};
    int16_t pcm_[kChunk * 2] = {0};
    int16_t rs_[(kChunk + 2) * 2] = {0};
    double step_ = 1.0, rsPos_ = 0.0;
    int rsHave_ = 0;
    bool resampling_ = false;
    uint32_t lastRev_ = 0, autoDbHash_ = 0;
    int counter_ = 0, nameCounter_ = 0;
    long tick_ = 0;
    bool wantDisplay_ = false;
    long long lastDisplay_ = 0;
};

// The same entry as MPC_PLUGIN_ENTRY, plus a wrapped effSetChunk and effSetProgram: an "MPCP" chunk loads with engine writes held
// back (the engine state in its extra part is the truth); a 1.0.x chunk (the engine's "quality=..." text) goes to the engine as before.
// A program pick in the PRESET menu loads that preset.
namespace {
VstIntPtr (*g_origDispatcher)(AEffect*, VstInt32, VstInt32, VstIntPtr, void*, float) = nullptr;

VstIntPtr m72Dispatcher(AEffect* e, VstInt32 opcode, VstInt32 index, VstIntPtr value, void* ptr, float opt)
{
    Model72Plugin* p = static_cast<Model72Plugin*>(e->object);
    if (opcode == effSetChunk && p && ptr && value > 0)
    {
        if (value >= 4 && std::memcmp(ptr, "MPCP", 4) == 0)
        {
            p->loading_.store(true);
            const VstIntPtr r = g_origDispatcher(e, opcode, index, value, ptr, opt);
            p->loading_.store(false);
            p->requestResync();
            return r;
        }
        return p->loadLegacy(static_cast<const char*>(ptr), (size_t)value) ? 1 : 0;
    }
    if (opcode == effSetProgram && p)
    {
        const VstIntPtr r = g_origDispatcher(e, opcode, index, value, ptr, opt);
        p->programPicked((int)value);
        return r;
    }
    return g_origDispatcher(e, opcode, index, value, ptr, opt);
}
} // namespace

#ifdef M72_TEST   // offline test hooks (tests/host_test.cpp); absent from the release build
extern "C" MPC_EXPORT void m72_dbg_tick(AEffect* e) { static_cast<Model72Plugin*>(e->object)->dbgTick(); }
extern "C" MPC_EXPORT int m72_dbg_engine(AEffect* e, const char* key, char* out, int n)
{
    const std::string s = static_cast<Model72Plugin*>(e->object)->dbgEngine(key);
    std::snprintf(out, (size_t)n, "%s", s.c_str());
    return (int)s.size();
}
extern "C" MPC_EXPORT int m72_dbg_favs(AEffect* e) { return static_cast<Model72Plugin*>(e->object)->dbgFavCount(); }
extern "C" MPC_EXPORT void m72_dbg_no_repeat_guard(AEffect* e) { static_cast<Model72Plugin*>(e->object)->dbgNoRepeatGuard(); }
extern "C" MPC_EXPORT void m72_dbg_no_ignore(AEffect* e) { static_cast<Model72Plugin*>(e->object)->dbgNoIgnore(); }
#endif

extern "C" MPC_EXPORT AEffect* VSTPluginMain(audioMasterCallback host)
{
    if (host != nullptr && host(nullptr, audioMasterVersion, 0, 0, nullptr, 0.0f) == 0) return nullptr;   // host is VST1 only
    AEffect* e = mpc::detail::createEffect(new Model72Plugin(), host);
    if (e && !g_origDispatcher) g_origDispatcher = e->dispatcher;
    if (e) e->dispatcher = m72Dispatcher;
    return e;
}
