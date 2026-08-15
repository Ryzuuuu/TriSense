# TriSense Mute Mode — Sign Language Dataset Attribution & Ethics

This document cites the public sign language datasets utilized for training and validating the **TriSense Mute Mode 3D Sign Language Classifier** (`SignLanguageClassifier`).

---

## 1. Primary Dataset: WLASL (Word-Level American Sign Language)

* **Paper:** *Word-level Deep Sign Language Recognition from Video: A New Large-scale Dataset and Methods Comparison*, Dongxu Li, Cristian Rodriguez, Xin Yu, and Hongdong Li, IEEE/CVF Winter Conference on Applications of Computer Vision (WACV), 2020.
* **Repository & Index:** [GitHub - dxli94/WLASL](https://github.com/dxli94/WLASL) (`WLASL_v0.3.json`).
* **Description:** WLASL is a large-scale American Sign Language (ASL) dataset featuring over 2,000 distinct words signed by deaf signers and native ASL instructors across diverse lighting, backgrounds, and camera angles.
* **License & Usage:** Released under academic/research non-commercial terms. TriSense utilizes only extracted 3D spatial landmark coordinate trajectories (`(30, 126)` NumPy float32 tensors) without distributing raw copyrighted video footage.

---

## 2. Evaluated (Not Used): ASL Citizen

* **Paper:** *ASL Citizen: A Community-Sourced Dataset for American Sign Language Recognition*, A. Desai, T. J. W. Wang, M. S. W. Chen, et al., Advances in Neural Information Processing Systems (NeurIPS), 2023.
* **Repository & Index:** [Microsoft / ASL Citizen](https://www.microsoft.com/en-us/research/project/asl-citizen/).
* **Description:** A community-driven ASL dataset featuring vocabulary recordings from Deaf and hard-of-hearing signers. Evaluated as a fallback source for words sparsely represented in WLASL, but **not used** — access requires a Kaggle account and data use agreement, which was not pursued for this project.

---

## 3. Tensor Storage Schema

Extracted gesture clips are stored locally as normalized 3D hand keypoint sequences:
* **Directory Structure:** `mute_mode/dataset/<word>/sample_{NN:02d}.npy`
* **Tensor Shape:** `(30, 126)` float32 array
  * **Axis 0 (30):** Fixed 30-frame temporal sliding window. Duration varies with source video FPS (e.g. ~1.5s at 20 FPS, ~1.0s at 30 FPS) since the buffer is a fixed frame-count window, not a fixed time window.
  * **Axis 1 (126):** Two hands × 21 MediaPipe keypoints × 3 coordinates (`X, Y, Z`), normalized relative to wrist origin (`wrist = (0, 0, 0)`) and bounding box span (`scale_factor`).

---

## 4. Ethical Commitment

All datasets are utilized strictly for open-source assistive hardware research. Attribution and authorship rights remain entirely with the original Deaf creators, ASL educators, and academic dataset curators.
