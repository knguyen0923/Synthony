"""5 clips from MAESTRO v3.0.0's official **test** split (not train --
this must stay a legitimate held-out eval), spanning 5 composers and
~65-170s durations. Paths are relative to the root folder inside both
MAESTRO zips (`maestro-v3.0.0/`), taken verbatim from
maestro-v3.0.0.csv's audio_filename/midi_filename columns."""
from __future__ import annotations

CLIPS: list[dict] = [
    {
        "name": "scriabin_entragete",
        "audio_filename": "2009/MIDI-Unprocessed_11_R1_2009_06-09_ORIG_MID--AUDIO_11_R1_2009_11_R1_2009_07_WAV.wav",
        "midi_filename": "2009/MIDI-Unprocessed_11_R1_2009_06-09_ORIG_MID--AUDIO_11_R1_2009_11_R1_2009_07_WAV.midi",
    },
    {
        "name": "debussy_etude7",
        "audio_filename": "2004/MIDI-Unprocessed_SMF_17_R1_2004_03-06_ORIG_MID--AUDIO_20_R2_2004_12_Track12_wav--1.wav",
        "midi_filename": "2004/MIDI-Unprocessed_SMF_17_R1_2004_03-06_ORIG_MID--AUDIO_20_R2_2004_12_Track12_wav--1.midi",
    },
    {
        "name": "scarlatti_k525",
        "audio_filename": "2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.wav",
        "midi_filename": "2008/MIDI-Unprocessed_09_R3_2008_01-07_ORIG_MID--AUDIO_09_R3_2008_wav--2.midi",
    },
    {
        "name": "liszt_gnomenreigen",
        "audio_filename": "2008/MIDI-Unprocessed_14_R1_2008_01-05_ORIG_MID--AUDIO_14_R1_2008_wav--3.wav",
        "midi_filename": "2008/MIDI-Unprocessed_14_R1_2008_01-05_ORIG_MID--AUDIO_14_R1_2008_wav--3.midi",
    },
    {
        "name": "schubert_impromptu90no4",
        "audio_filename": "2015/MIDI-Unprocessed_R2_D1-2-3-6-7-8-11_mid--AUDIO-from_mp3_03_R2_2015_wav--1.wav",
        "midi_filename": "2015/MIDI-Unprocessed_R2_D1-2-3-6-7-8-11_mid--AUDIO-from_mp3_03_R2_2015_wav--1.midi",
    },
]
