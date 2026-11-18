// Offline host test for the native front end (src/Model72Plugin.cpp) with the real CA-72 engine, under ASan/UBSan (tests/run.sh).
// A fake VST2 host drives it: identity and the frozen order, the PRESET menu, sound (LO and HI), knobs / switches / whole numbers,
// the QUALITY (parameter 0) nudge, the readouts, a state round trip into a second instance, a 1.0.1 project chunk
// (tests/fixtures/state-1.0.1.txt, made by the released engine), bad chunks, a host at 48 kHz, and user presets with the keyboard.
// Prints OK at the end, or the failures and exits 1.
#include "mpc_vst2_abi.h"
#include "params_gen.h"
#include "presets_gen.h"

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

extern "C" AEffect* VSTPluginMain(audioMasterCallback);
extern "C" void m72_dbg_tick(AEffect*);
extern "C" int m72_dbg_engine(AEffect*, const char*, char*, int);
extern "C" void m72_dbg_no_ignore(AEffect*);
extern "C" int m72_dbg_favs(AEffect*);
extern "C" void m72_dbg_no_repeat_guard(AEffect*);

static std::atomic<int> g_automate[kNumParams];
static std::atomic<int> g_updateDisplay{0};
static int g_fail = 0;

static VstIntPtr host(AEffect*, VstInt32 op, VstInt32 idx, VstIntPtr, void*, float)
{
    if (op == audioMasterAutomate && idx >= 0 && idx < kNumParams) g_automate[idx]++;
    if (op == audioMasterVersion) return 2400;
    if (op == audioMasterUpdateDisplay) g_updateDisplay++;
    return 0;
}

#define CHECK(c, ...) do { if (c) { std::printf("  ok   "); } else { std::printf("  FAIL "); g_fail++; } std::printf(__VA_ARGS__); std::printf("\n"); } while (0)

static int idx(const char* key)
{
    for (int i = 0; i < kNumParams; i++) if (!std::strcmp(g_pspecs[i].key, key)) return i;
    std::printf("no param %s\n", key); std::exit(2);
}
static float norm(int i, float plain) { const PSpec& s = g_pspecs[i]; return s.max > s.min ? (plain - s.min) / (s.max - s.min) : 0.f; }
static float plainOf(AEffect* e, int i) { const PSpec& s = g_pspecs[i]; return s.min + e->getParameter(e, i) * (s.max - s.min); }
static std::string eng(AEffect* e, const char* k) { static char b[8192]; m72_dbg_engine(e, k, b, sizeof b); return b; }
static int engi(AEffect* e, const char* k) { return (int)std::lround(std::atof(eng(e, k).c_str())); }
static float engf(AEffect* e, const char* k) { return (float)std::atof(eng(e, k).c_str()); }
static std::string disp(AEffect* e, int i) { char b[128] = {0}; e->dispatcher(e, effGetParamDisplay, i, 0, b, 0); return b; }
static std::string progName(AEffect* e, int i) { char b[64] = {0}; e->dispatcher(e, effGetProgramNameIndexed, i, 0, b, 0); return b; }
static int prog(AEffect* e) { return (int)e->dispatcher(e, effGetProgram, 0, 0, nullptr, 0); }
static bool near(float a, float b) { return std::fabs(a - b) < 0.011f; }

static double g_rms;
static void run(AEffect* e, int blocks, const std::vector<std::vector<uint8_t>>& midi = {}, int frames = 128)
{
    float L[256], R[256], *out[2] = {L, R};
    double acc = 0; long n = 0;
    for (int b = 0; b < blocks; b++)
    {
        if (b == 0 && !midi.empty())
        {
            std::vector<VstMidiEvent> ev(midi.size());
            std::vector<char> buf(sizeof(VstEvents) + sizeof(VstEvent*) * midi.size());
            VstEvents* evs = reinterpret_cast<VstEvents*>(buf.data());
            evs->numEvents = (VstInt32)midi.size();
            for (size_t k = 0; k < midi.size(); k++)
            {
                std::memset(&ev[k], 0, sizeof ev[k]);
                ev[k].type = kVstMidiType; ev[k].byteSize = sizeof(VstMidiEvent);
                ev[k].deltaFrames = (VstInt32)(k * 17 % frames);   // sample-accurate split
                for (size_t j = 0; j < 3 && j < midi[k].size(); j++) ev[k].midiData[j] = (char)midi[k][j];
                evs->events[k] = reinterpret_cast<VstEvent*>(&ev[k]);
            }
            e->dispatcher(e, effProcessEvents, 0, 0, evs, 0);
        }
        e->processReplacing(e, nullptr, out, frames);
        for (int i = 0; i < frames; i++) { acc += (double)L[i] * L[i] + (double)R[i] * R[i]; n += 2; }
    }
    g_rms = n ? std::sqrt(acc / n) : 0;
}
static void settle(AEffect* e, int blocks = 4) { run(e, blocks); m72_dbg_tick(e); }

static AEffect* open(const char* what, float rate = 44100.f)
{
    AEffect* e = VSTPluginMain(host);
    e->dispatcher(e, effSetSampleRate, 0, 0, nullptr, rate);
    e->dispatcher(e, effSetBlockSize, 0, 256, nullptr, 0);
    e->dispatcher(e, effMainsChanged, 0, 1, nullptr, 0);
    settle(e);
    std::printf("%s: opened\n", what);
    return e;
}
static void close(AEffect* e) { e->dispatcher(e, effMainsChanged, 0, 0, nullptr, 0); e->dispatcher(e, effClose, 0, 0, nullptr, 0); }
static std::vector<uint8_t> chunk(AEffect* e)
{
    void* p = nullptr;
    const VstIntPtr n = e->dispatcher(e, effGetChunk, 0, 0, &p, 0);
    return n > 0 && p ? std::vector<uint8_t>((uint8_t*)p, (uint8_t*)p + n) : std::vector<uint8_t>();
}
static VstIntPtr setChunk(AEffect* e, std::vector<uint8_t> c) { return e->dispatcher(e, effSetChunk, 0, (VstIntPtr)c.size(), c.data(), 0); }
static std::vector<uint8_t> readFile(const std::string& p)
{
    std::ifstream f(p, std::ios::binary);
    return std::vector<uint8_t>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}
static double notes(AEffect* e, int blocks = 200)
{
    run(e, blocks, {{0x90, 48, 100}, {0x90, 55, 100}});
    const double on = g_rms;
    run(e, 2, {{0x80, 48, 0}, {0x80, 55, 0}});
    run(e, 1500);
    return on;
}

int main(int argc, char** argv)
{
    const std::string fixtures = argc > 1 ? argv[1] : "tests/fixtures";
    const int QUAL = idx("quality"), MODE = idx("mode"), VOICES = idx("voices"), CUT = idx("cutoff"), EMPH = idx("emphasis"),
              R1 = idx("osc1_range"), O2ON = idx("osc2_on"), SPREAD = idx("spread"), AUTODB = idx("auto_db"), PRIO = idx("note_priority"),
              DRIVE = idx("drive"), FDEC = idx("filter_decay");

    std::printf("== identity\n");
    AEffect* a = open("A");
    char name[64] = {0};
    a->dispatcher(a, effGetEffectName, 0, 0, name, 0);
    CHECK(a->uniqueID == (VstInt32)M72_EXPECT_UID, "uid %08x", (unsigned)a->uniqueID);
    CHECK(!std::strcmp(name, M72_EXPECT_NAME), "name \"%s\"", name);
    CHECK(a->numParams == 118, "118 params: the 72 of 1.0.1 + user presets and keyboard (%d)", a->numParams);
    CHECK(a->dispatcher(a, effGetVendorVersion, 0, 0, nullptr, 0) == 2000, "version 2000");
    {
        int bad = 0, i = 0;
        std::ifstream f("vst/params.lock");
        std::string line;
        while (std::getline(f, line)) if (!line.empty() && (i >= kNumParams || line != g_pspecs[i++].key)) bad++;
        CHECK(i == 118 && bad == 0, "order = vst/params.lock (%d keys, %d differ)", i, bad);
        CHECK(QUAL == 0 && idx("retrigger") == 71 && kFavAdd == 72, "quality 0, retrigger 71 (the 1.0.1 table), then fav_add 72");
        char pn[64] = {0};
        a->dispatcher(a, effGetParamName, 0, 0, pn, 0);
        CHECK(!std::strcmp(pn, "Quality"), "param 0 is \"%s\"", pn);
    }

    std::printf("== PRESET menu\n");
    CHECK(a->numPrograms == kFactory + kFavSlots && kFactory == 19, "%d programs: 19 factory + %d user", a->numPrograms, kFavSlots);
    CHECK(progName(a, 0) == "Felt Bass" && progName(a, 18) == "Cycle of Fifths", "factory names (\"%s\" .. \"%s\")", progName(a, 0).c_str(), progName(a, 18).c_str());
    CHECK(progName(a, 19) == "U01 --", "user slots after them (\"%s\")", progName(a, 19).c_str());

    std::printf("== sound\n");
    double on = notes(a);
    run(a, 50);
    CHECK(on > 1e-3, "LO: notes are audible (rms %.4f)", on);
    CHECK(g_rms < on * 0.05, "note off releases (rms %.5f)", g_rms);

    std::printf("== knobs, switches, whole numbers\n");
    a->setParameter(a, CUT, norm(CUT, -1.5f));
    a->setParameter(a, EMPH, norm(EMPH, 6.25f));
    settle(a);
    CHECK(near(engf(a, "cutoff"), -1.5f) && near(engf(a, "emphasis"), 6.25f), "CUTOFF -1.5, EMPHASIS 6.25 -> engine %s, %s", eng(a, "cutoff").c_str(), eng(a, "emphasis").c_str());
    CHECK(disp(a, CUT) == "-1.50", "CUTOFF shows \"%s\"", disp(a, CUT).c_str());
    a->setParameter(a, O2ON, 1.0f);
    a->setParameter(a, R1, norm(R1, 2));
    a->setParameter(a, MODE, norm(MODE, 1));
    settle(a);
    CHECK(engi(a, "osc2_on") == 1 && engi(a, "osc1_range") == 2 && engi(a, "mode") == 1, "OSC 2 on, OSC 1 RANGE 16', MODE POLY");
    CHECK(disp(a, R1) == "16'", "RANGE shows \"%s\"", disp(a, R1).c_str());
    a->setParameter(a, VOICES, norm(VOICES, 4));
    settle(a);
    a->setParameter(a, VOICES, norm(VOICES, 4.3f));
    settle(a);
    CHECK(engi(a, "voices") == 5, "a small turn up moves VOICES one step (engine %d)", engi(a, "voices"));
    CHECK(std::lround(plainOf(a, VOICES)) == 5, "and the host is told where it landed (%.2f)", plainOf(a, VOICES));
    a->setParameter(a, PRIO, norm(PRIO, 1.6f));
    settle(a);
    a->setParameter(a, PRIO, norm(PRIO, 1.2f));
    settle(a);
    CHECK(engi(a, "note_priority") == 1, "a small turn down moves PRIORITY to Last (%d)", engi(a, "note_priority"));

    std::printf("== QUALITY (parameter 0) nudge\n");
    a->setParameter(a, QUAL, 1.0f);
    run(a, 2);
    a->setParameter(a, QUAL, 0.0f);
    run(a, 2);
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    run(a, 2);
    CHECK(engi(a, "quality") == 0, "a nudge to HI and straight back leaves it LO (%d)", engi(a, "quality"));
    a->setParameter(a, QUAL, 1.0f);
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    run(a, 2);
    CHECK(engi(a, "quality") == 1, "a held change applies (HI)");
    a->setParameter(a, MODE, 0.0f);
    settle(a);
    for (int i = 0; i < 600 && engi(a, "hi_ready") != 1; i++) { std::this_thread::sleep_for(std::chrono::milliseconds(50)); run(a, 1); }
    CHECK(engi(a, "hi_ready") == 1, "HI's circuit filter was built");
    on = notes(a, 100);
    CHECK(on > 1e-3, "HI: notes are audible (rms %.4f)", on);
    a->setParameter(a, QUAL, 0.0f);
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    settle(a);

    std::printf("== readouts\n");
    a->setParameter(a, DRIVE, norm(DRIVE, 12));
    settle(a);
    run(a, 20);
    settle(a);
    CHECK(!disp(a, AUTODB).empty() && disp(a, AUTODB).find("dB") != std::string::npos, "AUTO dB shows \"%s\"", disp(a, AUTODB).c_str());
    a->setParameter(a, MODE, norm(MODE, 1));
    a->setParameter(a, SPREAD, norm(SPREAD, 80));
    settle(a);
    run(a, 10, {{0x90, 48, 100}, {0x90, 52, 100}, {0x90, 55, 100}});
    settle(a);
    int lit = 0;
    for (int d = 0; d < kDots; d++) lit += plainOf(a, kDot1 + d) > 0.0f;
    CHECK(lit >= 2, "the STEREO field shows the playing voices (%d dots lit)", lit);
    const std::string before = eng(a, "state");
    a->setParameter(a, kDot1, 0.5f);
    a->setParameter(a, AUTODB, 0.7f);
    settle(a);
    CHECK(eng(a, "state") == before, "writing a readout changes nothing in the engine");
    run(a, 2, {{0xB0, 123, 0}});
    run(a, 400);

    std::printf("== programs\n");
    m72_dbg_no_ignore(a);
    g_updateDisplay = 0;
    a->dispatcher(a, effSetProgram, 0, 2, nullptr, 0);
    settle(a);
    CHECK(engi(a, "patch") == 1 && std::lround(plainOf(a, idx("patch"))) == 1, "Feedback Funk: PATCH on, the control follows");
    CHECK(g_updateDisplay > 0, "one display update for the new program (%d)", g_updateDisplay.load());
    CHECK(prog(a) == 2, "the PRESET menu is on it");

    std::printf("== state round trip\n");
    a->setParameter(a, CUT, norm(CUT, 2.5f));
    a->setParameter(a, FDEC, norm(FDEC, 7.75f));
    settle(a);
    const std::string stA = eng(a, "state");
    std::vector<uint8_t> ca = chunk(a);
    CHECK(ca.size() > 4 && !std::memcmp(ca.data(), "MPCP", 4), "MPC chunk (%zu bytes)", ca.size());
    AEffect* b = open("B");
    CHECK(setChunk(b, ca) == 1, "B takes A's chunk");
    settle(b);
    CHECK(eng(b, "state") == stA, "B's engine state = A's");
    CHECK(near(plainOf(b, CUT), 2.5f) && near(plainOf(b, FDEC), 7.75f) && std::lround(plainOf(b, idx("patch"))) == 1,
          "B's controls show CUTOFF 2.5, F DECAY 7.75, PATCH on");
    b->dispatcher(b, effSetProgram, 0, 2, nullptr, 0);   // the host re-picks the saved program right after a load: no reload
    settle(b);
    CHECK(eng(b, "state") == stA, "the post-load re-pick keeps the project's edits");

    std::printf("== 1.0.1 project chunk\n");
    {
        std::vector<uint8_t> c = readFile(fixtures + "/state-1.0.1.txt");
        c.push_back(0);   // the wrapper saved the text with its NUL
        const std::string want(reinterpret_cast<const char*>(c.data()));
        AEffect* e = open("1.0.1 chunk");
        CHECK(c.size() > 100 && setChunk(e, c) == 1, "takes it (%zu bytes)", c.size());
        settle(e);
        CHECK(eng(e, "state") == want, "  the engine state is the saved one");
        CHECK(std::lround(plainOf(e, MODE)) == 1 && std::lround(plainOf(e, VOICES)) == 6 && std::lround(plainOf(e, O2ON)) == 1 &&
              near(plainOf(e, CUT), -1.75f) && near(plainOf(e, EMPH), 6.5f) && std::lround(plainOf(e, PRIO)) == 1 && std::lround(plainOf(e, idx("patch"))) == 1,
              "  the saved sound shows: POLY 6, OSC 2 on, CUTOFF %.2f, EMPHASIS %.2f, PRIORITY Last, PATCH on", plainOf(e, CUT), plainOf(e, EMPH));
        CHECK(notes(e, 50) > 1e-3, "  it plays");
        std::vector<uint8_t> again = chunk(e);   // saved again by this build, then reloaded
        AEffect* f = open("  re-saved");
        setChunk(f, again);
        settle(f);
        CHECK(eng(f, "state") == want, "  re-saved by this build and reloaded: unchanged");
        close(f);
        close(e);
    }

    std::printf("== bad chunks\n");
    {
        const std::string st = eng(b, "state");
        CHECK(setChunk(b, {'x', 'y', 'z', 0}) == 0, "garbage is refused");
        settle(b);
        CHECK(eng(b, "state") == st, "  unchanged");
        CHECK(setChunk(b, {'q', 'u', 'a', 'l', 'i', 't', 'y', '=', 'z', ';', 'c', 'u', 't', 'o', 'f', 'f', '=', '9', '9', 0}) == 1, "a broken 1.0.1 text is taken");
        settle(b);
        CHECK(engi(b, "quality") == 0 && near(engf(b, "cutoff"), 5.0f), "  bad values ignored, out of range clamped (cutoff %s)", eng(b, "cutoff").c_str());
        std::vector<uint8_t> trunc(ca.begin(), ca.begin() + ca.size() / 2);
        setChunk(b, trunc);
        settle(b);
        CHECK(eng(b, "state").compare(0, 8, "quality=") == 0, "a truncated MPC chunk: no crash, still a valid state");
    }

    std::printf("== a host at 48 kHz\n");
    {
        AEffect* h = open("48k", 48000.f);
        run(h, 100, {{0x90, 57, 100}}, 200);
        CHECK(g_rms > 1e-3, "plays through the resampler (rms %.4f)", g_rms);
        run(h, 2, {{0x80, 57, 0}}, 200);
        close(h);
    }

    std::printf("== user presets\n");
    {
        const int n0 = m72_dbg_favs(a);
        m72_dbg_no_ignore(a);
        a->dispatcher(a, effSetProgram, 0, 3, nullptr, 0);
        settle(a);
        a->setParameter(a, CUT, norm(CUT, 1.25f));
        settle(a);
        const std::string saved = eng(a, "state");
        auto key = [&](const char* k) { const int i = idx(k); m72_dbg_no_repeat_guard(a); a->setParameter(a, i, 1.0f); settle(a); a->setParameter(a, i, 0.0f); };
        key("fav_add");
        CHECK(std::lround(plainOf(a, kKbOpen)) == 1 && m72_dbg_favs(a) == n0, "+PRESET opens the keyboard, nothing saved yet");
        CHECK(disp(a, kFavName) == "Tenor Pluck_", "it starts from the program's name (\"%s\")", disp(a, kFavName).c_str());
        a->setParameter(a, CUT, norm(CUT, 4.0f));   // a change while typing is not in the preset: +PRESET took the sound
        settle(a);
        for (int i = 0; i < 25; i++) key("kb_bksp");
        CHECK(disp(a, kFavName) == "_", "delete empties it");
        for (const char* k : {"kb_f", "kb_a", "kb_t", "kb_space", "kb_7", "kb_2", "kb_shift", "kb_x"}) key(k);
        CHECK(disp(a, kFavName) == "Fat 72X_", "typed \"Fat 72X\": capital first letter, SHIFT for one letter (\"%s\")", disp(a, kFavName).c_str());
        {   // one tap reported twice (no 0 between) types one letter
            const int i = idx("kb_q");
            m72_dbg_no_repeat_guard(a);
            a->setParameter(a, i, 1.0f); settle(a);
            a->setParameter(a, i, 1.0f); settle(a);
            a->setParameter(a, i, 0.0f);
            CHECK(disp(a, kFavName) == "Fat 72Xq_", "a doubled tap types once (\"%s\")", disp(a, kFavName).c_str());
        }
        key("kb_bksp"); key("kb_bksp");
        key("kb_save");
        CHECK(std::lround(plainOf(a, kKbOpen)) == 0 && m72_dbg_favs(a) == n0 + 1, "SAVE stores it and closes the keyboard (%d)", m72_dbg_favs(a));
        const int slot = kFactory + n0;
        char want[32];
        std::snprintf(want, sizeof want, "U%02d Fat 72", n0 + 1);
        CHECK(progName(a, slot) == want, "PRESET menu: \"%s\"", progName(a, slot).c_str());
        CHECK(prog(a) == slot, "the new preset is the picked entry");
        key("fav_add");
        key("kb_z");
        key("kb_cancel");
        CHECK(std::lround(plainOf(a, kKbOpen)) == 0 && m72_dbg_favs(a) == n0 + 1, "CANCEL closes it without saving");
        key("kb_a");
        CHECK(m72_dbg_favs(a) == n0 + 1, "keys do nothing while it is closed");
        a->dispatcher(a, effSetProgram, 0, 10, nullptr, 0);
        settle(a);
        CHECK(eng(a, "state") != saved, "another program in between");
        a->dispatcher(a, effSetProgram, 0, slot, nullptr, 0);
        settle(a);
        CHECK(eng(a, "state") == saved && near(plainOf(a, CUT), 1.25f), "picking it restores it (CUTOFF %.2f)", plainOf(a, CUT));
        AEffect* e2 = open("E (reads the presets file)");
        CHECK(m72_dbg_favs(e2) == n0 + 1 && progName(e2, slot) == progName(a, slot), "a new instance reads it from model72-presets.dat");
        close(e2);
        a->setParameter(a, kFavDel, 1.0f);
        settle(a); settle(a);
        a->setParameter(a, kFavDel, 0.0f);
        CHECK(m72_dbg_favs(a) == n0 && progName(a, slot).compare(4, 2, "--") == 0, "-PRESET deletes the picked one (\"%s\")", progName(a, slot).c_str());
        a->dispatcher(a, effSetProgram, 0, 0, nullptr, 0);
        settle(a);
        a->setParameter(a, kFavDel, 1.0f);
        settle(a);
        a->setParameter(a, kFavDel, 0.0f);
        CHECK(progName(a, 0) == "Felt Bass", "-PRESET on a factory preset does nothing");
    }

    close(b);
    close(a);
    if (g_fail) { std::printf("%d FAILED\n", g_fail); return 1; }
    std::printf("OK\n");
    return 0;
}
