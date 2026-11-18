# Model-72 2.0.0

Model-72 now runs on Akai's MPC Plugin SDK. It is the same instrument and the same plugin: same name, same id and the same parameters, so
projects saved with 1.x open with their sound. Install it over 1.x.

**New**
- **Save your own presets.** A PRESETS tab: **+ SAVE PRESET** names the current sound with an on-screen keyboard and adds it to the PRESET
  menu (U01 to U64); **- DELETE PRESET** removes the picked one. Kept in the plugin's folder and kept when you update.
- **The PITCH wheel works.** It was only painted on the OUTPUT tab before. Drag it or turn its Q-Link; BEND RANGE sets how far.
- **QUALITY is no longer part of a preset.** Picking a preset keeps LO / HI as you set it. A new Model-72 starts in HI on Gen2
  (MPC Live III and other 64-bit MPCs), in LO on the Force and Gen1.
- **Q-Links in blocks of four**, each a group printed on the panel, with the MPC's Q-Link overlay. MIXER FILTER has two sub-tabs (filter,
  mixer). Double tap a knob for the large knob view.
- A one-folder download for MPC OS 3.10.1 and later (`-mpc-sdk.zip`), next to the per-device zips.

**Downloads**: `*-mpc-armv7.zip` for the Force and Gen1 MPCs (MPC OS 3.9.x and later), `*-mpc-aarch64.zip` for Gen2 (MPC Live III and kin),
`*-mpc-sdk.zip`: one folder for both, MPC OS 3.10.1+. Restart MPC after installing (skins load at its start).

**Tested**: on an MPC Live III (skin, Q-Links, presets, QUALITY, pitch wheel). The Force build passes the offline tests; 2.0 has not been run on
a Force yet (1.0 was). Loading a 1.x project was tested offline with a state the 1.x engine wrote. Reports welcome.
