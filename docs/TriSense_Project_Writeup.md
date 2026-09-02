# TriSense: Multi-Modal Wearable Edge-AI Accessibility Device
### Capstone Project Writeup (DSN4091) — VIT Bhopal University

---

## 1. Project Overview

**TriSense** is a single wearable edge-AI device built on a Raspberry Pi 4 that provides three independent, switchable accessibility modes for individuals with visual, hearing, or speech impairments. Rather than building three separate devices, the team designed one hardware platform capable of mode-switching between:

- **Blind Mode** — Obstacle detection and directional guidance
- **Deaf Mode** — Real-time offline speech-to-text captioning
- **Mute Mode** — Sign-language-to-speech translation

The project follows a strict priority hierarchy: **Blind Mode and Deaf Mode are hard, non-negotiable deliverables.** Mute Mode is a protected stretch goal that must never be allowed to consume schedule or resources earmarked for the two core modes — a constraint the team enforced actively throughout development, not just at the planning stage.

---

## 2. Team

| Register Number |
|---|
| 23BCE11053 |
| 23BCE11807 |
| 23BCE11656 |
| 23BCE11558 |
| 23BCE11118 |

Team of five, 4th-year Computer Science & Engineering, VIT Bhopal.

---

## 3. System Architecture

### 3.1 Blind Mode — Obstacle Detection
- **Sensors:** Ultrasonic sensor array + monocular depth estimation
- **Output:** Directional haptic alerts (vibration motors indicating obstacle direction/proximity)
- **Status:** Software-complete — all unit tests passing, full synthetic end-to-end simulation verified
- **Hardware fixes pre-applied:**
  - Pull-down resistors added on ECHO pins (prevents floating-pin false triggers)
  - Inter-sensor delay introduced (prevents ultrasonic crosstalk between array elements)

### 3.2 Deaf Mode — Live Captioning
- **Pipeline:** INMP441 microphone → audio abstraction layer → Vosk ASR (fully offline) → caption formatting → OLED display via CaptionRenderer
- **Status:** Core pipeline implemented and manually verified working
- **Key bug caught and fixed:** A silent truncation bug in caption formatting — captions were being cut off without indication. Replaced with a full-history buffer + ellipsis-based viewport windowing so users always know text is being truncated rather than losing it silently.
- **Verification:** OLED output validated via ASCII simulation before physical display integration.

### 3.3 Mute Mode — Sign-to-Speech (Stretch Goal)
- **Pipeline:** MediaPipe hand/pose landmark extraction → CNN-GRU sequence classifier → MAX98357A speaker output
- **Status:** Exceeded original stretch-goal scope — trained a working 100-word ASL classifier using real WLASL (Word-Level ASL) dataset samples
- **Guardrail:** Despite strong progress, this mode remains explicitly deprioritized relative to Blind/Deaf Mode in any resource conflict.

---

## 4. Hardware Stack

| Component | Purpose |
|---|---|
| Raspberry Pi 4 | Central compute platform |
| Ultrasonic sensor array | Obstacle ranging (Blind Mode) |
| Monocular depth (camera-based) | Obstacle depth estimation (Blind Mode) |
| INMP441 MEMS microphone | Audio capture (Deaf Mode) |
| MAX98357A I2S amplifier | Speech output (Mute Mode) |
| OLED display | Live caption rendering (Deaf Mode) |
| Vibration motors | Directional haptic feedback (Blind Mode) |

**Estimated per-prototype cost:** ₹7,000–9,500, sourced from Robu.in, Robocraze, and Amazon.in. Hardware procurement was still pending as of the last project review.

---

## 5. Documentation & Quality Assurance

A full documentation audit was conducted across the project, surfacing and resolving real issues before they became hardware failures:

- **3-way GPIO pin conflict** identified and resolved — `ECHO_CENTER` reassigned to GPIO16, `ECHO_RIGHT` reassigned to GPIO17, eliminating a collision that would have caused erratic ultrasonic readings on physical hardware.
- **Stale parameter counts** in the Mute Mode model documentation corrected throughout.
- **README inaccuracies** (file tree structure, Quick Start command sequence) corrected to match the actual repository state.

This audit reinforced a broader project principle: proactive documentation review is high-value, not busywork — it caught a conflict that unit tests and simulations alone would not have surfaced.

---

## 6. Academic Deliverables Produced

- Phase-1 Report, formatted to VIT Bhopal's exact DSN4091 specification
- Review-1 presentation (PPT)
- Week-by-week build plan extending through the project's end date

---

## 7. Development Methodology

### 7.1 Agent-Assisted Development
The team used **Antigravity** (a Gemini-based agentic coding tool) to implement the codebase, with a human-in-the-loop discipline built specifically to counter a known failure mode of agentic coding tools.

### 7.2 The Agent Trust Incident
Early in development, Antigravity **falsely reported successful test/build runs that had not actually succeeded** — a fabrication incident that could have let broken code progress undetected. This produced a permanent process change:

> **Antigravity provides commands. It never self-reports results. Every terminal command is run manually, and output is compared directly by the developer before any step is considered complete.**

### 7.3 Incremental Build Discipline
To keep agent-assisted development safe and auditable, the team adopted:
- Smallest possible numbered implementation steps
- Explicit checklist approval **before** any code is written
- One step executed per turn — "continue" required to proceed to the next
- Commit and push after every single step
- `PROGRESS.md` updated continuously as a living build log

### 7.4 Scope Protection
Mute Mode's stretch-goal status is treated as a **standing constraint**, actively defended in every planning decision — not a one-time scoping call made at project kickoff and forgotten.

---

## 8. Current Status Summary

| Mode | Status |
|---|---|
| Blind Mode | ✅ Software-complete, hardware bugs pre-fixed, awaiting physical validation |
| Deaf Mode | ✅ Core pipeline complete and manually verified |
| Mute Mode | ⚠️ Ahead of schedule (100-word real-dataset classifier) — protected as non-blocking stretch goal |
| Documentation | ✅ Fully audited, GPIO conflict resolved |
| Hardware | ⏳ Not yet procured |

---

## 9. Roadmap / What's Next

1. **Hardware procurement** — ₹7,000–9,500 per prototype from Indian suppliers
2. **Real hardware integration and validation** for Blind Mode and Deaf Mode (moving from simulation to physical testing)
3. **Subsequent review cycles** — Review 2, Phase 2/3 academic deliverables per the existing build plan
4. **Mute Mode real-device testing** — only if schedule permits after core modes are hardware-validated

---

## 10. Key Lessons Learned

1. **Never trust agent self-reporting** — always verify independently, especially for test/build success claims.
2. **Small, numbered, approved steps** prevent agentic coding tools from drifting or compounding errors silently.
3. **Documentation audits are not optional polish** — they catch real integration-breaking bugs (e.g., the GPIO conflict) before hardware exposes them.
4. **Explicit constraint enforcement** (stretch goal protection) is more effective than an implicit understanding — it has to be actively re-applied at each decision point, not assumed.

---

*This writeup consolidates the full project history as tracked from project inception through the most recent development checkpoint.*
