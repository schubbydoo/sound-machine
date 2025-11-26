# Sound Machine – Channel Knob Update - Requirements Document (Draft v0.1)

## 1. Summary of Operation

This document describes the planned enhancements to the current Sound Machine, adding a vintage-style 4-position rotary channel selector knob, named profiles, descriptive metadata for audio files, game-mode support, and a database-backed configuration system.

The system will allow the user to rotate a physical knob to switch between up to four sound profiles. Each profile contains assignments of audio files to the 16 hardware buttons. The web UI will allow uploading multiple audio files at once, auto-assigning them to buttons, renaming profiles, editing audio metadata, and generating an Answer Key for gameplay (guess-the-source game). A SQLite database will store all profile and audio metadata.

The update should be implemented in a modular fashion such that functions are separate from the existing functions that provide the audio playout and LED operation. That is, this update should be somewhat transparent to the existing audio playout. The audio playout should simply be playing the audio assigned to the selected profile and button assignments. The dB is the source of truth and should be simply queried by the audio playout system when a button is pressed. The user should be able to turn the knob to choose a profile and press any button and the associated audio file is played out. If there is no audio file assigned, a default audio file stating “a sound is not assigned at this time” is played.

There should be a way to print an answer key for the game. That is, the ability to print the dB entries for each profile so it’s easy for the player that is guessing what the sounds are to grade their guessing accuracy.

This document is intended for markup and revision as requirements evolve. Once the enhancement is complete, the system README will be updated to include the enhancements.

## 2. Requirements (Draft)

- **Physical Hardware**
    - Physical 4-position rotary switch connected directly to Raspberry Pi Zero 2W GPIO pins.
    - One GPIO pin represents one channel (4 pins total), with internal pull-ups and common-to-ground wiring.
    - Channel selection determines the active profile when `USE_CHANNEL_KNOB = true`.
    - **Channel, wire color, GPIO assignments:**
        - Channel 1: Yellow, GPIO22
        - Channel 2: Orange, GPIO23
        - Channel 3: Red, GPIO24
        - Channel 4: Brown, GPIO25
        - Common: Black, GND

- **Profiles**
    - Profiles, once established, can be easily assigned to a different channel. For example, the profile “Classic Horror” can be changed from channel one to channel 4 without changing any of the button assignments. This is simply a DB entry change for channel number assignment.
    - Conflicts should be gracefully handled (e.g., two different profiles should not be allowed to be assigned to a single channel).
    - Profiles have user-friendly names (e.g., “Classic Horror”).
    - Profile contains button-to-audio-file assignments for each of the 16 buttons.
    - Profiles can be renamed, created, and deleted without removing audio files.

- **Web UI**
    - **Bulk Upload:** Ability to upload multiple audio files simultaneously. This requirement is an enhancement to the existing upload functionality.
    - **Auto-Assign:** Ability to auto-assign uploaded files to button slots.
    - **Manual Reassignment:** Manual reassignment of any button to any audio file. (Existing functionality to be preserved/enhanced).
    - **Profile Management:** Rename, create, and delete profiles.
    - **Metadata Editing:** Edit audio metadata including source description, category, and tags.
    - **Channel Mapping:** Manage channel-to-profile mapping.
    - **Answer Key:** Generate printable Answer Key for gameplay.

- **Database**
    - SQLite database stores profiles, audio files, button mappings, and channel-profile mappings.

- **Answer Key Output**
    - Includes: Channel, Profile name, Button number, File name, Source description, Category, and optional Hint.

