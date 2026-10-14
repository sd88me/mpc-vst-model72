//! Draws the MPC skin's art with upstream's own panel renderer (the worn skin): each tab's
//! background, and for every control a filmstrip or on/off pair cut from renders of the whole
//! panel with that control at each position, so that a frame sits exactly over its place in the
//! background. Writes `vst/art/*.png` and `vst/layout.conf`.
//!
//!     cargo run --release -- <repo>/vst

use ca72_panel::art::{self, PANEL_H};
use ca72_panel::controls::{Control, Kind};
use ca72_panel::strip::{self, Bank, Readout, StripRenderer, StripScene};
use ca72_panel::{CONTROLS, Pixmap, Renderer, Scene, Skin};
use std::collections::HashMap;
use std::fmt::Write as _;

/// The plugin area on the MPC's screen, and the layout's y for its top (Force Shadow's).
const SW: u32 = 1280;
const SH: u32 = 628;
const Y_OFF: i64 = 86;

/// A part of the drawing (units: left, top, right, bottom) placed at `at` (pixels) on a tab.
#[derive(Clone, Copy)]
struct Piece {
    src: [f64; 4],
    at: (f64, f64),
    /// Rows of its own (units, top and bottom) that are blank panel: tiled above and below it
    /// to the bands, where it is shorter than the tab (a strip section beside the panel).
    pad: Option<(f64, f64)>,
}

struct Tab {
    name: &'static str,
    scale: f64,
    /// Where the pieces' origin is on the tab (pixels), inside the wood.
    origin: (f64, f64),
    /// The wood around the panel: left, top, right, bottom (pixels; 0 none).
    wood: [i64; 4],
    /// Blank panel tiled over a strip the drawing leaves (pixels: x, y, w, h), from a block
    /// (x, y, w, h) of the tab.
    fill: Vec<([i64; 4], [i64; 4])>,
    pieces: Vec<Piece>,
    qlinks: &'static [&'static str],
}

/// Blank panel (units of the drawing: under the mixer, between its knobs and its title), tiled
/// behind every tab's pieces: what they leave between them reads as panel.
const BLANK: [f64; 4] = [1640.0, 742.0, 1700.0, 790.0];

/// The parameters this port has (its params.json keys) among the panel's controls.
const OURS: &[&str] = &[
    "tune", "osc_mod", "glide", "mod_mix", "osc1_range", "osc2_range", "osc3_range",
    "osc2_frequency", "osc3_frequency", "osc1_waveform", "osc2_waveform", "osc3_waveform",
    "osc3_control", "osc1_volume", "osc1_on", "ext_volume", "ext_on", "osc2_volume", "osc2_on",
    "noise_volume", "noise_on", "osc3_volume", "osc3_on", "noise_type", "filter_mode",
    "filter_mod", "keyboard_control_1", "keyboard_control_2", "cutoff", "emphasis",
    "contour_amount", "filter_attack", "filter_decay", "filter_sustain", "loudness_attack",
    "loudness_decay", "loudness_sustain", "volume", "main_output", "a440", "feedback", "quality",
    "glide_on", "decay_on", "mod_wheel", "voices", "entropy", "drive", "level", "note_priority",
    "retrigger", "spread", "inner", "double",
];

/// Positions an option parameter has, where the panel's control has more (QUALITY: LO and HI
/// of upstream's LO, HI, ULTRA).
fn options_of(c: &Control) -> Option<Vec<f64>> {
    match (c.param, c.kind) {
        ("quality", _) => Some(vec![0.0, 0.5]),
        (_, Kind::Toggle { .. }) => Some(vec![0.0, 0.5, 1.0]),
        (_, Kind::Selector(_)) => Some((0..6).map(|i| f64::from(i) / 5.0).collect()),
        (_, Kind::Rocker { .. }) => Some(vec![0.0, 1.0]),
        _ => None,
    }
}

/// Which of the strip's tabs are lit: MODE's, AUTO GAIN, VOICES PLAYED AS's, PLACEMENT's.
#[derive(Clone, Copy, Default)]
struct Lit {
    mode: usize,
    auto: bool,
    stereo: usize,
    placement: usize,
}

/// Renders of the whole drawing at one scale.
struct Drawing {
    scale: f64,
    panel: Renderer,
    strip: StripRenderer,
}

impl Drawing {
    fn new(scale: f64) -> Drawing {
        Drawing {
            scale,
            panel: Renderer::with_skin(Skin::Worn, scale, 1.0),
            strip: StripRenderer::new(scale),
        }
    }

    /// The whole drawing with the controls at `values` (normalised) and MODE at `mode`.
    fn render(&mut self, values: &[f64], mode: usize) -> Pixmap {
        self.render_with(values, Lit { mode, ..Lit::default() })
    }

    /// As [`Drawing::render`], the strip's tabs lit as `lit` has them.
    fn render_with(&mut self, values: &[f64], lit: Lit) -> Pixmap {
        let mut scene = Scene::default();
        scene.values.copy_from_slice(values);
        self.panel.render(&scene);
        let ss = StripScene {
            mode: Some(lit.mode),
            auto: lit.auto,
            stereo: Some(lit.stereo),
            placement: Some(lit.placement),
            // (The field drawn empty: a still picture cannot show where voices sound.)
            field: ca72_panel::strip::Field::Scatter(Vec::new()),
            readouts: std::array::from_fn(|_| (String::new(), false)),
            ..StripScene::default()
        };
        // (The whole drawing as changed: the strip keeps its copy of what is under it, the
        // strip's knobs among it, until told.)
        let (fw, fh) = (self.panel.frame().width() as i32, self.panel.frame().height() as i32);
        self.strip.render(&ss, self.panel.frame(), Some([0, 0, fw, fh]));
        let mut all = self.panel.frame().clone();
        let top = (PANEL_H * self.scale).round() as usize;
        let w = all.width() as usize;
        let sf = self.strip.frame();
        let rows = (sf.height() as usize).min(all.height() as usize - top);
        for y in 0..rows {
            let n = w.min(sf.width() as usize) * 4;
            let (from, to) = (y * sf.width() as usize * 4, (top + y) * w * 4);
            all.data_mut()[to..to + n].copy_from_slice(&sf.data()[from..from + n]);
        }
        all
    }
}

/// `src`'s pixels from (x, y), `w` by `h`, into `dst` at (dx, dy) (clipped).
fn blit(src: &Pixmap, x: i64, y: i64, w: i64, h: i64, dst: &mut Pixmap, dx: i64, dy: i64) {
    let (sw, sh, dw, dh) = (src.width() as i64, src.height() as i64, dst.width() as i64, dst.height() as i64);
    for j in 0..h {
        let (sy, ty) = (y + j, dy + j);
        if sy < 0 || sy >= sh || ty < 0 || ty >= dh {
            continue;
        }
        for i in 0..w {
            let (sx, tx) = (x + i, dx + i);
            if sx < 0 || sx >= sw || tx < 0 || tx >= dw {
                continue;
            }
            let (s, t) = (((sy * sw + sx) * 4) as usize, ((ty * dw + tx) * 4) as usize);
            let px: [u8; 4] = src.data()[s..s + 4].try_into().unwrap();
            dst.data_mut()[t..t + 4].copy_from_slice(&px);
        }
    }
}

fn pix(w: u32, h: u32) -> Pixmap {
    Pixmap::new(w, h).expect("a picture's size")
}

/// The tab's picture from a whole drawing: its pieces, each where it goes.
fn compose(tab: &Tab, whole: &Pixmap) -> Pixmap {
    let mut bg = pix(SW, SH);
    bg.fill(resvg::tiny_skia::Color::from_rgba8(14, 13, 12, 255));
    let (ox, oy) = tab.origin;
    {
        let s = tab.scale;
        let [x0, y0, x1, y1] = BLANK;
        let (bx, by) = ((x0 * s).round() as i64, (y0 * s).round() as i64);
        let (bw, bh) = (((x1 - x0) * s).round() as i64, ((y1 - y0) * s).round() as i64);
        let (top, bottom) = (tab.wood[1], i64::from(SH) - tab.wood[3]);
        let mut y = top;
        while y < bottom {
            let mut x = 0;
            while x < i64::from(SW) {
                blit(whole, bx, by, bw.min(i64::from(SW) - x), bh.min(bottom - y), &mut bg, x, y);
                x += bw;
            }
            y += bh;
        }
    }
    for p in &tab.pieces {
        let s = tab.scale;
        let [x0, y0, x1, y1] = p.src;
        let (sx, sy) = ((x0 * s).round() as i64, (y0 * s).round() as i64);
        let (w, h) = (((x1 - x0) * s).round() as i64, ((y1 - y0) * s).round() as i64);
        let (dx, dy) = ((ox + p.at.0).round() as i64, (oy + p.at.1).round() as i64);
        blit(whole, sx, sy, w, h, &mut bg, dx, dy);
        if let Some((r0, r1)) = p.pad {
            let (ry, rh) = ((r0 * s).round() as i64, ((r1 - r0) * s).round().max(1.0) as i64);
            let (top, bottom) = (tab.wood[1], i64::from(SH) - tab.wood[3]);
            let mut y = dy - rh;
            while y + rh > top {
                let y0 = y.max(top);
                blit(whole, sx, ry + (y0 - y), w, rh - (y0 - y), &mut bg, dx, y0);
                y -= rh;
            }
            let mut y = dy + h;
            while y < bottom {
                blit(whole, sx, ry, w, rh.min(bottom - y), &mut bg, dx, y);
                y += rh;
            }
        }
    }
    for &([fx, fy, fw, fh], [bx, by, bw, bh]) in &tab.fill {
        let src = bg.clone();
        let mut y = fy;
        while y < fy + fh {
            let mut x = fx;
            while x < fx + fw {
                blit(&src, bx, by, bw.min(fx + fw - x), bh.min(fy + fh - y), &mut bg, x, y);
                x += bw;
            }
            y += bh;
        }
    }
    wood(&mut bg, whole, tab);
    bg
}

/// The walnut around the panel, cut from the drawing's own (its top rail): bands along the
/// top and bottom, the grain across; cheeks at the sides, the grain upright; a dark seam where
/// the wood meets the panel.
fn wood(bg: &mut Pixmap, whole: &Pixmap, tab: &Tab) {
    let s = tab.scale;
    let (wy0, wy1) = ((14.0 * s).round() as i64, (112.0 * s).round() as i64);
    let ww = whole.width() as i64;
    // (Plain walnut only: clear of the ends' trim and of the name badge at the right.)
    let (xa, xb) = ((60.0 * s).round() as i64, (2300.0 * s).round() as i64);
    let get = |x: i64, y: i64| -> [u8; 4] {
        let (x, y) = (xa + x.rem_euclid(xb - xa), wy0 + y.rem_euclid(wy1 - wy0));
        let i = ((y * ww + x) * 4) as usize;
        whole.data()[i..i + 4].try_into().unwrap()
    };
    let [l, t, r, b] = tab.wood;
    let (w, h) = (i64::from(SW), i64::from(SH));
    let mut put = |x: i64, y: i64, px: [u8; 4]| {
        let i = ((y * w + x) * 4) as usize;
        bg.data_mut()[i..i + 4].copy_from_slice(&px);
    };
    for y in 0..h {
        for x in 0..w {
            let px = if y < t {
                Some(get(x + 40, y + (wy1 - wy0 - t) / 2))
            } else if y >= h - b {
                Some(get(w - 1 - x + 20, h - 1 - y + (wy1 - wy0 - b) / 2))
            } else if x < l {
                Some(get(y + 200, x + 10))
            } else if x >= w - r {
                Some(get(y + 900, w - 1 - x + 10))
            } else {
                None
            };
            if let Some(px) = px {
                put(x, y, px);
            }
        }
    }
    let seam = [10, 8, 6, 255];
    for y in 0..h {
        for x in 0..w {
            let edge = (t > 0 && (y == t || y == t + 1) && x >= l && x < w - r)
                || (b > 0 && (y == h - b - 1 || y == h - b - 2) && x >= l && x < w - r)
                || (l > 0 && (x == l || x == l + 1) && y >= t && y < h - b)
                || (r > 0 && (x == w - r - 1 || x == w - r - 2) && y >= t && y < h - b);
            if edge {
                put(x, y, seam);
            }
        }
    }
}

/// Where a point of the drawing lands on the tab, if a piece shows it.
fn place(tab: &Tab, (x, y): (f64, f64)) -> Option<(f64, f64)> {
    tab.pieces.iter().find_map(|p| {
        let [x0, y0, x1, y1] = p.src;
        (x >= x0 && x <= x1 && y >= y0 && y <= y1)
            .then(|| {
                (
                    tab.origin.0 + p.at.0 + (x - x0) * tab.scale,
                    tab.origin.1 + p.at.1 + (y - y0) * tab.scale,
                )
            })
    })
}

fn even(x: f64) -> i64 {
    let n = x.ceil() as i64;
    n + (n & 1)
}

/// A copy within a tab's picture (pixels: from x, y, w by h, to x, y), covering print this port
/// has nothing behind (a neighbouring section's cut title, ULTRA, AUTO GAIN) with blank panel.
type Patch = (i64, i64, i64, i64, i64, i64);

fn patch(bg: &mut Pixmap, (sx, sy, w, h, dx, dy): Patch) {
    let src = bg.clone();
    blit(&src, sx, sy, w, h, bg, dx, dy);
}

/// Blank panel (`src`, units) tiled over `dst` (units), on tab `t`.
fn patch_units(bg: &mut Pixmap, t: &Tab, dst: [f64; 4], src: [f64; 4]) {
    let px = |x: f64, y: f64| place(t, (x, y)).map(|(a, b)| (a.round() as i64, b.round() as i64));
    let (Some((dx0, dy0)), Some((dx1, dy1)), Some((sx0, sy0)), Some((sx1, sy1))) =
        (px(dst[0], dst[1]), px(dst[2], dst[3]), px(src[0], src[1]), px(src[2], src[3]))
    else {
        eprintln!("warning: {}: a patch outside the tab", t.name);
        return;
    };
    let (sw, sh) = (sx1 - sx0, sy1 - sy0);
    let copy = bg.clone();
    let mut y = dy0;
    while y < dy1 {
        let mut x = dx0;
        while x < dx1 {
            blit(&copy, sx0, sy0, sw.min(dx1 - x), sh.min(dy1 - y), bg, x, y);
            x += sw;
        }
        y += sh;
    }
}

/// What each control is drawn as on the MPC.
#[derive(Clone, Copy, PartialEq, Debug)]
enum Art {
    /// A filmstrip of n frames, square (a knob, a selector, a lever), r the layout's radius.
    Strip(usize),
    /// Off and on pictures (a rocker).
    Pair,
    /// A vertical filmstrip (the MODULATION wheel).
    Wheel(usize),
}

fn art_of(c: &Control) -> Art {
    match c.kind {
        Kind::Knob { .. } => Art::Strip(64),
        Kind::Selector(_) => Art::Strip(6),
        Kind::Toggle { .. } => Art::Strip(options_of(c).map_or(3, |o| o.len())),
        Kind::Rocker { .. } => Art::Pair,
        Kind::Wheel { .. } => Art::Wheel(48),
    }
}

/// The value (normalised, as the drawing takes it) of frame `f` of `n`.
fn frame_value(c: &Control, f: usize, n: usize) -> f64 {
    match options_of(c) {
        Some(o) => o[f.min(o.len() - 1)],
        None => f as f64 / (n - 1).max(1) as f64,
    }
}

struct Placed {
    i: usize,
    c: &'static Control,
    /// The crop on the tab: left, top, width, height (pixels).
    bx: (i64, i64, i64, i64),
    art: Art,
}

fn main() {
    let out = std::path::PathBuf::from(std::env::args().nth(1).expect("the port's vst/ folder"));
    let art_dir = out.join("art");
    std::fs::create_dir_all(&art_dir).unwrap();

    let (sw, sh) = (f64::from(SW), f64::from(SH));
    // MOD_LAYOUT: what sits left of MODIFIERS: "voices" (the strip's VOICES section; PERFORM
    // then has the left-hand column) or "column" (the left-hand column; PERFORM has VOICES).
    let voices_on_mod = std::env::var("MOD_LAYOUT").map_or(true, |v| v != "column");
    // OSCILLATORS sets the wood: the panel below its own rail to the mixer's end across the
    // width, and the bands what is left; every tab has those bands.
    let x1 = 1848.0;
    let s1 = sw / x1;
    let band = ((sh - (PANEL_H - art::TOP) * s1) / 2.0).floor();
    let inner = sh - 2.0 * band;
    let rail = PANEL_H + strip::RAIL;
    // MODIFIERS: the panel from the mixer's edge to its silver end at OSCILLATORS' size, at the
    // right; at the left, the strip's VOICES section or the left-hand column, centred on it.
    let x2 = 1826.0;
    let w2 = (art::W - x2) * s1;
    let strip_y = ((inner - (art::H - rail) * s1) / 2.0).round();
    // (VOICES after the panel's silver end, as a section of its own, its blank rows between the
    // rail and MODE's title tiled up and down to the bands.)
    let mod_left = if voices_on_mod {
        Piece { src: [395.0, rail, strip::SECTIONS[1].1, art::H], at: (w2, strip_y), pad: Some((rail + 6.0, rail + 30.0)) }
    } else {
        Piece { src: [0.0, rail, strip::SECTIONS[0].1, art::H], at: (sw - strip::SECTIONS[0].1 * s1, strip_y), pad: Some((rail + 6.0, rail + 30.0)) }
    };
    // PERFORM: the other of the two at the left, OUTPUT at the right (the silver end), from the
    // banks' titles to the sections' own.
    let (y3a, y3b) = (PANEL_H + 140.0, art::H - 12.0);
    let s3 = inner / (y3b - y3a);
    let out_x = sw - (art::W - strip::SECTIONS[3].0) * s3;
    let perform_left = if voices_on_mod {
        Piece { src: [0.0, y3a, strip::SECTIONS[0].1, y3b], at: (0.0, 0.0), pad: None }
    } else {
        Piece { src: [336.0, y3a, strip::SECTIONS[1].1, y3b], at: (0.0, 0.0), pad: None }
    };
    // STEREO: the strip's section with a little of each neighbour, centred.
    let (y4a, y4b) = (PANEL_H + 140.0, art::H - 15.0);
    let (x4a, x4b) = (strip::SECTIONS[2].0 - 44.0, strip::SECTIONS[2].1 + 44.0);
    let s4 = (sw / (x4b - x4a)).min(inner / (y4b - y4a));
    let x4 = ((sw - (x4b - x4a) * s4) / 2.0).floor();
    let wood = [0, band as i64, 0, band as i64];
    let tabs = vec![
        Tab {
            name: "OSCILLATORS",
            scale: s1,
            origin: (0.0, band),
            wood,
            fill: vec![],
            pieces: vec![Piece { src: [0.0, art::TOP, x1, PANEL_H], at: (0.0, 0.0), pad: None }],
            qlinks: &[
                "tune", "glide", "mod_mix", "osc1_volume", "osc1_range", "osc2_range", "osc3_range", "osc2_volume",
                "osc1_waveform", "osc2_waveform", "osc3_waveform", "osc3_volume", "osc2_frequency",
                "osc3_frequency", "noise_volume", "ext_volume",
            ],
        },
        Tab {
            name: "MODIFIERS",
            scale: s1,
            origin: (0.0, band),
            wood,
            fill: vec![],
            pieces: vec![Piece { src: [x2, art::TOP, art::W, PANEL_H], at: (0.0, 0.0), pad: None }, mod_left],
            qlinks: if voices_on_mod {
                &[
                    "cutoff", "emphasis", "contour_amount", "volume", "filter_attack", "filter_decay",
                    "filter_sustain", "feedback", "loudness_attack", "loudness_decay", "loudness_sustain",
                    "voices", "entropy", "mode", "quality", "bass_comp",
                ]
            } else {
                &[
                    "cutoff", "emphasis", "contour_amount", "volume", "filter_attack", "filter_decay",
                    "filter_sustain", "feedback", "loudness_attack", "loudness_decay", "loudness_sustain",
                    "mod_wheel", "note_priority", "quality", "bass_comp", "patch",
                ]
            },
        },
        Tab {
            name: "PERFORM",
            scale: s3,
            origin: (0.0, band),
            wood,
            fill: vec![],
            pieces: vec![perform_left, Piece { src: [strip::SECTIONS[3].0, y3a, art::W, y3b], at: (out_x, 0.0), pad: None }],
            qlinks: if voices_on_mod {
                &["drive", "level", "midi_bend_range", "auto_gain", "mod_wheel", "note_priority", "patch"]
            } else {
                &["voices", "entropy", "drive", "level", "midi_bend_range", "mode", "auto_gain"]
            },
        },
        Tab {
            name: "STEREO",
            scale: s4,
            origin: (x4, band),
            wood,
            fill: vec![],
            pieces: vec![Piece { src: [x4a, y4a, x4b, y4b], at: (0.0, 0.0), pad: None }],
            qlinks: &["spread", "inner", "double", "played_as", "placement"],
        },
    ];
    // Print this port has nothing behind, under blank panel tiled from beside it (units of the
    // drawing: covered, then the blank block): MIXER's title cut at MODIFIERS' left edge;
    // QUALITY's shutter (which opens for ULTRA, not here) and ULTRA.
    let unit_patches: HashMap<&str, Vec<([f64; 4], [f64; 4])>> = HashMap::from([(
        // (The KEYBOARD CONTROL and FILTER MODULATION legends' ends at OSCILLATORS' right edge.)
        "OSCILLATORS",
        vec![([1824.0, 330.0, x1, 680.0], [1824.0, 690.0, x1, 790.0])],
    ), (
        "MODIFIERS",
        vec![
            ([2950.0, 140.0, 3100.0, 284.0], [2950.0, 494.0, 3100.0, 530.0]),
            ([2985.0, 318.0, 3100.0, 372.0], [2985.0, 494.0, 3100.0, 530.0]),
        ],
    )]);
    let patches: HashMap<&str, Vec<Patch>> = HashMap::new();
    pix(4, 4).save_png(art_dir.join("clear.png")).unwrap();
    let mut layout = String::new();
    layout.push_str(
        "# generated by skin/ (cargo run --release -- vst): upstream's panel, drawn by its own renderer, cut into\n\
         # a background per tab and a filmstrip or on/off pair per control, each frame over its own place.\n\
         theme_bg=0e0d0c\ntheme_panel=0e0d0c\ntheme_ink=e8e2d0\ntheme_ink_dim=8f8878\ntheme_accent=e8862b\n\
         theme_accent_hi=ffb15c\ntheme_lcd=0e0d0c\ntheme_seg_active=0e0d0c\ntheme_seg_inactive=0e0d0c\n\
         theme_seg_active_tx=0e0d0c\ntheme_box=0e0d0c\n",
    );

    for t in &tabs {
        let mut d = Drawing::new(t.scale);
        let defaults: Vec<f64> = CONTROLS.iter().map(|c| default_value(c.param)).collect();
        let whole = d.render(&defaults, 0);
        let mut bg = compose(t, &whole);
        for &p in patches.get(t.name).map(Vec::as_slice).unwrap_or(&[]) {
            patch(&mut bg, p);
        }
        for &(dst, src) in unit_patches.get(t.name).map(Vec::as_slice).unwrap_or(&[]) {
            patch_units(&mut bg, t, dst, src);
        }
        if t.name == "OSCILLATORS" {
            // The Instruments browser's tile: the oscillator bank, halved.
            let mut cut = pix(540, 220);
            blit(&bg, 300, 40, 540, 220, &mut cut, 0, 0);
            ca72_panel::skin::resample(&cut, 270, 110).save_png(art_dir.join("tile.png")).unwrap();
        }
        let bg_name = format!("{}.png", t.name.to_lowercase());
        bg.save_png(art_dir.join(&bg_name)).unwrap();
        let _ = writeln!(layout, "\n[tab {}]\nart file=art/{bg_name} fit=stretch", t.name);

        // The controls this tab shows.
        let mut placed: Vec<Placed> = Vec::new();
        for (i, c) in CONTROLS.iter().enumerate() {
            if !OURS.contains(&c.param) {
                continue;
            }
            let Some((x, y)) = place(t, c.centre()) else { continue };
            if t.name == "MODIFIERS" && c.centre().0 < 1840.0 && c.centre().1 < PANEL_H {
                continue; // (The mixer's are on OSCILLATORS.)
            }
            let [l, top, r, b] = art::bounds(&c.kind);
            let art = art_of(c);
            let (cx, cy) = (x.round() as i64, y.round() as i64);
            let bx = match art {
                Art::Strip(_) => {
                    let side = even(2.0 * l.abs().max(top.abs()).max(r).max(b) * t.scale) + 2;
                    (cx - side / 2, cy - side / 2, side, side)
                }
                Art::Pair | Art::Wheel(_) => {
                    let (w, h) = (even((r - l) * t.scale) + 2, even((b - top) * t.scale) + 2);
                    (cx - w / 2, cy - h / 2, w, h)
                }
            };
            placed.push(Placed { i, c, bx, art });
        }
        for a in &placed {
            for b in &placed {
                let (p, q) = (a.bx, b.bx);
                if a.i < b.i && p.0 < q.0 + q.2 && q.0 < p.0 + p.2 && p.1 < q.1 + q.3 && q.1 < p.1 + p.3 {
                    eprintln!("warning: {}: {} and {} overlap", t.name, a.c.param, b.c.param);
                }
            }
        }
        // Each kind's frames: every control of the kind at the frame's position, the rest at
        // their defaults.
        let mut frames: HashMap<usize, Vec<Pixmap>> = HashMap::new();
        let most = placed
            .iter()
            .map(|p| match p.art {
                Art::Strip(n) | Art::Wheel(n) => n,
                Art::Pair => 2,
            })
            .max()
            .unwrap_or(0);
        for f in 0..most {
            let mut values = defaults.clone();
            let mut any = false;
            for p in &placed {
                let n = match p.art {
                    Art::Strip(n) | Art::Wheel(n) => n,
                    Art::Pair => 2,
                };
                if f < n {
                    values[p.i] = frame_value(p.c, f, n);
                    any = true;
                }
            }
            if !any {
                continue;
            }
            let pic = compose(t, &d.render(&values, 0));
            for p in &placed {
                let n = match p.art {
                    Art::Strip(n) | Art::Wheel(n) => n,
                    Art::Pair => 2,
                };
                if f < n {
                    let (x, y, w, h) = p.bx;
                    let mut cut = pix(w as u32, h as u32);
                    blit(&pic, x, y, w, h, &mut cut, 0, 0);
                    frames.entry(p.i).or_default().push(cut);
                }
            }
        }
        for p in &placed {
            let fr = &frames[&p.i];
            let (x, y, w, h) = p.bx;
            let (cx, cy) = (x + w / 2, y + h / 2 + Y_OFF);
            let key = p.c.param;
            match p.art {
                Art::Strip(n) | Art::Wheel(n) => {
                    let mut s = pix(w as u32, (h as usize * n) as u32);
                    for (k, f) in fr.iter().enumerate() {
                        blit(f, 0, 0, w, h, &mut s, 0, k as i64 * h);
                    }
                    s.save_png(art_dir.join(format!("{key}.png"))).unwrap();
                    if let Art::Wheel(_) = p.art {
                        let _ = writeln!(layout, "slider_v cx={cx} cy={cy} w={w} h={h} label=\"\" key={key} strip=art/{key}.png frames={n} ns=0 vs=0");
                    } else {
                        let r = (w - 8) / 2;
                        let _ = writeln!(layout, "knob cx={cx} cy={cy} r={r} label=\"\" key={key} strip=art/{key}.png frames={n} ns=0 vs=0 bw={w}");
                    }
                }
                Art::Pair => {
                    fr[0].save_png(art_dir.join(format!("{key}_off.png"))).unwrap();
                    fr[1].save_png(art_dir.join(format!("{key}_on.png"))).unwrap();
                    let _ = writeln!(layout, "toggle cx={cx} cy={cy} label=\"\" key={key} img=art/{key}_off.png img_on=art/{key}_on.png w={w} h={h} ns=0");
                }
            }
        }
        // The strip's own (banks, readouts, field, AUTO GAIN, BEND) wherever its sections are.
        strip_extras(&mut d, t, &defaults, &art_dir, &mut layout);
        if t.name == "MODIFIERS" {
            // BASS COMP: A-440's blue switch beside it, its name in MPC's own type.
            let a440 = CONTROLS.iter().position(|c| c.param == "a440").unwrap();
            let [l, top, r, b] = art::bounds(&CONTROLS[a440].kind);
            let (rw, rh) = (even((r - l) * t.scale) + 2, even((b - top) * t.scale) + 2);
            let (ax, ay) = place(t, CONTROLS[a440].centre()).unwrap();
            for (v, name) in [(0.0, "bass_comp_off"), (1.0, "bass_comp_on")] {
                let mut vals = defaults.clone();
                vals[a440] = v;
                let pic = compose(t, &d.render(&vals, 0));
                let mut cut = pix(rw as u32, rh as u32);
                blit(&pic, ax.round() as i64 - rw / 2, ay.round() as i64 - rh / 2, rw, rh, &mut cut, 0, 0);
                cut.save_png(art_dir.join(format!("{name}.png"))).unwrap();
            }
            let (bx, by) = place(t, (2853.0, 505.0)).unwrap();
            let _ = writeln!(layout, "toggle cx={} cy={} label=\"BASS COMP\" key=bass_comp img=art/bass_comp_off.png img_on=art/bass_comp_on.png w={rw} h={rh} bw=120",
                bx.round() as i64, by.round() as i64 + Y_OFF);
            // PATCH: a cable from the output into EXTERNAL INPUT (FEEDBACK's), plugged at PHONES.
            let (jx, jy, jr, _) = art::jacks().into_iter().min_by(|a, b| {
                let d = |j: &(f64, f64, f64, bool)| (j.0 - 2900.0).powi(2) + (j.1 - 730.0).powi(2);
                d(a).total_cmp(&d(b))
            }).unwrap();
            let (cx, cy) = place(t, (jx, jy)).unwrap();
            let side = even(2.0 * jr * 1.25 * t.scale);
            let (x0, y0) = (cx.round() as i64 - side / 2, cy.round() as i64 - side / 2);
            let mut cut = pix(side as u32, side as u32);
            blit(&bg, x0, y0, side, side, &mut cut, 0, 0);
            cut.save_png(art_dir.join("patch_off.png")).unwrap();
            let _ = writeln!(layout, "toggle cx={} cy={} label=\"PATCH\" key=patch img=art/patch_off.png w={side} h={side} bw=110",
                x0 + side / 2, y0 + side / 2 + Y_OFF);
        }
        let q: Vec<&str> = t.qlinks.to_vec();
        let _ = writeln!(layout, "qlinks \"{}\" = {}", t.name, q.join(","));
        eprintln!("{}: {} controls, scale {:.4}", t.name, placed.len(), t.scale);
    }
    std::fs::write(out.join("layout.conf"), layout).unwrap();
}

/// The strip's own parts on tab `t`, each where its section is shown: MODE's, VOICES PLAYED
/// AS's and PLACEMENT's tabs (a picture an option, under clear segments that pick it), AUTO
/// GAIN, the readouts' live text, the stereo field, and MIDI BEND RANGE on a knob cap in the
/// blank panel left of DRIVE.
fn strip_extras(d: &mut Drawing, t: &Tab, defaults: &[f64], art_dir: &std::path::Path, layout: &mut String) {
    let s = t.scale;
    let lit = |i| Lit { mode: i, ..Lit::default() };
    bank(d, t, defaults, art_dir, layout, Bank::Mode, "mode", 3, &lit);
    let lit = |i| Lit { stereo: i, ..Lit::default() };
    bank(d, t, defaults, art_dir, layout, Bank::Stereo, "played_as", 2, &lit);
    let lit = |i| Lit { placement: i, ..Lit::default() };
    bank(d, t, defaults, art_dir, layout, Bank::Placement, "placement", 2, &lit);
    readouts(t, layout, &[
        (Readout::Voices, "voices"), (Readout::Entropy, "entropy"), (Readout::Drive, "drive"), (Readout::Level, "level"),
        (Readout::Auto, "auto_db"), (Readout::Width, "spread"), (Readout::Inner, "inner"), (Readout::Detune, "double"),
    ]);
    field(t, art_dir, layout);
    // AUTO GAIN's tab, off and lit.
    if let Some((ax, ay)) = place(t, Bank::Auto.tab(0)) {
        let (aw, ah) = (even(strip::TAB.0 * s) + 2, even(strip::TAB.1 * s) + 2);
        let (ax, ay) = (ax.round() as i64 - aw / 2, ay.round() as i64 - ah / 2);
        for (on, name) in [(false, "auto_gain_off"), (true, "auto_gain_on")] {
            let pic = compose(t, &d.render_with(defaults, Lit { auto: on, ..Lit::default() }));
            let mut cut = pix(aw as u32, ah as u32);
            blit(&pic, ax, ay, aw, ah, &mut cut, 0, 0);
            cut.save_png(art_dir.join(format!("{name}.png"))).unwrap();
        }
        let _ = writeln!(layout, "toggle cx={} cy={} label=\"\" key=auto_gain img=art/auto_gain_off.png img_on=art/auto_gain_on.png w={aw} h={ah} ns=0",
            ax + aw / 2, ay + ah / 2 + Y_OFF);
    }
    // MIDI BEND RANGE: LEVEL's knob cap (no dial: its own scale is MPC's value text).
    let level = CONTROLS.iter().position(|c| c.param == "level").unwrap();
    let (Some((lx, ly)), Some((bx, by))) = (place(t, CONTROLS[level].centre()), place(t, (2450.0, 1377.0))) else {
        return;
    };
    let side = even(2.0 * 44.0 * s);
    let (cx, cy) = (lx.round() as i64, ly.round() as i64);
    let n = 64;
    let mut strip_pic = pix(side as u32, (side * n) as u32);
    for f in 0..n {
        let mut v = defaults.to_vec();
        v[level] = f as f64 / (n - 1) as f64;
        let pic = compose(t, &d.render(&v, 0));
        blit(&pic, cx - side / 2, cy - side / 2, side, side, &mut strip_pic, 0, f * side);
    }
    // (Round: the cap alone, the panel under it showing through the corners.)
    let rr = (side as f64 / 2.0 - 1.0).powi(2);
    for f in 0..n {
        for y in 0..side {
            for x in 0..side {
                let (dx, dy) = (x as f64 - side as f64 / 2.0 + 0.5, y as f64 - side as f64 / 2.0 + 0.5);
                if dx * dx + dy * dy > rr {
                    let i = (((f * side + y) * side + x) * 4) as usize;
                    strip_pic.data_mut()[i..i + 4].copy_from_slice(&[0, 0, 0, 0]);
                }
            }
        }
    }
    strip_pic.save_png(art_dir.join("midi_bend_range.png")).unwrap();
    let (bx, by) = (bx.round() as i64, by.round() as i64);
    let _ = writeln!(layout, "knob cx={bx} cy={} r={} label=\"BEND\" key=midi_bend_range strip=art/midi_bend_range.png frames={n} ns=17 vs=20 bw=120",
        by + Y_OFF, (side - 8) / 2);
}

/// A bank of the strip's tabs for an option parameter: a picture of the bank with each option's
/// tab lit, under clear segments that pick it.
#[allow(clippy::too_many_arguments)]
fn bank(d: &mut Drawing, t: &Tab, defaults: &[f64], art_dir: &std::path::Path, layout: &mut String, b: Bank, key: &str,
        n: usize, lit: &dyn Fn(usize) -> Lit) {
    let s = t.scale;
    let (rx, ry, rw, rh) = b.recess();
    let Some((x0, y0)) = place(t, (rx, ry)) else { return };
    let (x0, y0, w, h) = (x0.round() as i64, y0.round() as i64, even(rw * s), even(rh * s));
    let mut files = Vec::new();
    for i in 0..n {
        let pic = compose(t, &d.render_with(defaults, lit(i)));
        let mut cut = pix(w as u32, h as u32);
        blit(&pic, x0, y0, w, h, &mut cut, 0, 0);
        cut.save_png(art_dir.join(format!("{key}_{i}.png"))).unwrap();
        files.push(format!("art/{key}_{i}.png"));
    }
    let _ = writeln!(layout, "picture x={x0} y={} w={w} h={h} key={key} files=\"{}\"", y0 + Y_OFF, files.join(","));
    // (The bank's middle: between its tabs.)
    let (ax, ay) = place(t, b.tab(0)).unwrap();
    let (bx, _) = place(t, b.tab(n - 1)).unwrap();
    let sw = ((strip::TAB.0 + 6.0) * s).round() as i64 - 2;
    let sh = (strip::TAB.1 * s).round() as i64;
    let blank = vec![" "; n].join(",");
    let _ = writeln!(layout, "enum_h cx={} cy={} label=\"\" key={key} options=\"{blank}\" sw={sw} sh={sh} img=art/clear.png img_on=art/clear.png",
        ((ax + bx) / 2.0).round() as i64, ay.round() as i64 + Y_OFF);
}

/// The stereo field: one display-only filmstrip a dot (DOT 1 to 10, set by the engine), each
/// frame an orange drop at its place across the field's window, the first none.
fn field(t: &Tab, art_dir: &std::path::Path, layout: &mut String) {
    let (dx, dy, dw, dh) = strip::DISPLAY;
    let (Some((x0, y0)), Some((x1, y1))) = (place(t, (dx, dy)), place(t, (dx + dw, dy + dh))) else { return };
    let (x0, y0, w, h) = (x0.round() as i64, y0.round() as i64, (x1 - x0).round() as i64, (y1 - y0).round() as i64);
    let n = 49usize;
    let r = (h as f64 * 0.16).max(5.0);
    let margin = r * 1.6;
    let mut s = pix(w as u32, (h as usize * n) as u32);
    for f in 1..n {
        let at = ((f as f64 / (n - 1) as f64) - 0.02) / 0.98;
        let cx = margin + at.clamp(0.0, 1.0) * (w as f64 - 2.0 * margin);
        let cy = h as f64 / 2.0;
        for y in 0..h {
            for x in 0..w {
                let d = ((x as f64 + 0.5 - cx).powi(2) + (y as f64 + 0.5 - cy).powi(2)).sqrt();
                // (A lit drop: a core with a glow round it.)
                let core = (r + 0.5 - d).clamp(0.0, 1.0);
                let glow = (1.0 - d / (2.6 * r)).clamp(0.0, 1.0).powi(2) * 0.55;
                let a = core.max(glow);
                if a > 0.0 {
                    let (cr, cg, cb) = if core > 0.0 { (255.0, 150.0, 70.0) } else { (232.0, 110.0, 40.0) };
                    let i = (((f as i64 * h + y) * w + x) * 4) as usize;
                    // (Premultiplied, as tiny-skia keeps pixels.)
                    s.data_mut()[i..i + 4].copy_from_slice(&[(cr * a) as u8, (cg * a) as u8, (cb * a) as u8, (255.0 * a) as u8]);
                }
            }
        }
    }
    s.save_png(art_dir.join("field.png")).unwrap();
    for k in 1..=10 {
        let _ = writeln!(layout, "meter cx={} cy={} w={w} h={h} key=dot_{k} strip=art/field.png frames={n}", x0 + w / 2, y0 + h / 2 + Y_OFF);
    }
}

/// Live text in the strip's readout windows.
fn readouts(t: &Tab, layout: &mut String, which: &[(Readout, &str)]) {
    let s = t.scale;
    for &(r, key) in which {
        let (x, y, ww, hh) = r.window();
        if let Some((px, py)) = place(t, (x + ww / 2.0, y + hh / 2.0)) {
            let _ = writeln!(layout, "readout cx={} cy={} w={} h={} label=\"\" key={key} tsize={} tcolor=ff9a3c talign=center",
                px.round() as i64, py.round() as i64 + Y_OFF, (ww * s * 0.9).round() as i64, (hh * s * 0.8).round() as i64, (hh * s * 0.5).round() as i64);
        }
    }
}

/// A control's value in the background (normalised): this port's defaults (params.json).
fn default_value(param: &str) -> f64 {
    match param {
        "osc1_range" | "osc2_range" | "osc3_range" => 0.6,
        "osc1_waveform" | "osc2_waveform" | "osc3_waveform" => 0.4,
        "osc3_control" | "osc1_on" | "keyboard_control_1" | "main_output" | "decay_on" => 1.0,
        "osc1_volume" | "osc2_volume" | "osc3_volume" | "noise_volume" | "loudness_sustain" => 0.8,
        "ext_volume" | "contour_amount" | "filter_sustain" | "tune" | "cutoff" | "osc2_frequency"
        | "osc3_frequency" | "pitch_wheel" => 0.5,
        "filter_decay" | "loudness_decay" => 0.4,
        "volume" => 1.0,
        "double" => 0.2,
        "voices" => 0.25,
        "level" => 30.0 / 42.0,
        _ => 0.0,
    }
}
