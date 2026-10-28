# MuJoCo によるアーム動作範囲の全探索（2026-10-26）

TB3 に載った OpenManipulator-X を MuJoCo で再現し、姿勢を網羅的に試して「動ける範囲」を求めた。機体には何も送っていない（機体から読んだのは robot_description とメッシュだけ）。

## 座標系・規約（sim_common.py の解析 FK と同じ）
- 原点 = joint2 の軸（base_link で x=-0.080, z=0.1675）。r = 前方、z = 上、pitch = 手先の下向き角 = a2+a3+a4（+は下向き、+90°で真下、-90°で真上）。
- q = /joint_states の値（指令に使う値）、a = URDF 側の関節角 = q + OFFSET、OFFSET = [0, 0.93, 0.07, -1.65]（カメラで実測済み）。
- 床は joint2 軸から -17.75 cm、上段の板の上面は -7.55 cm。

## ファイル
| ファイル | 中身 |
|---|---|
| `workspace.json` | 到達領域。r-z 1 cm × pitch 3°。`combos["<limit>|<env>"]` に、セルごとの可能な pitch の本数・最小/最大・区間、トルク余裕（最良/最悪、0/100/200/500 g）、yaw ごとの到達ビット。`web_vs_sim`＝画面とのずれ、`validation`＝実機確認済み姿勢の照合、`meta`＝仮定の一覧 |
| `joint_space.json` | 関節空間（q2,q3,q4 を ±180° の 2° 刻み、yaw=0）。使える q の範囲、各関節の周辺自由割合、(q2,q3) ごとの joint4 の自由な区間 |
| `sensitivity.json` | 許容めり込み・グリッパー開閉・肘の解・画面の限界を直した場合・トルク検算 |
| `workspace_rz.png` `workspace_pitch.png` `workspace_torque.png` `workspace_excluded.png` `workspace_yaw.png` `joint_space.png` | 図 |
| `omx_model.py` `sim_common.py` `mesh_parts.py` | モデル（URDF→MJCF、メッシュは凸分解）と評価関数 |
| `sweep.py` → `analyze.py` → `export.py` / `extra_checks.py` / `calibrate.py` | 全探索 → 集計 → 書き出し／感度／モデル検証 |
| `out/*.npz` | 生の結果（めり込み量、トルク、yaw ビット） |

再実行: `.venv\Scripts\python.exe sweep.py all; .venv\Scripts\python.exe export.py; .venv\Scripts\python.exe extra_checks.py`（22 並列で約 4 分）

## 使い方（webui に反映するとき）
- `combos["urdf_on_a|photo_solid"]` を基準に使う。セル番号は `ir = round((r + 0.12)/0.01)`, `iz = round((z + 0.20)/0.01)`、配列の添字は `ir*nz+iz`（nz=61）。`n_pitch[idx] > 0` ならそのセルは届く。`pitch_runs_deg["ir,iz"]` が取れる pitch の区間（度）。
- 関節の限界は、URDF の限界を q に直した値を使うのが正しい（`sensitivity.json` の `q_limits_urdf_converted`）: joint2 [-2.7207, 0.6408]、joint3 [-1.0125, 1.3123]、joint4 [-0.1407, 3.1416] rad。今の arm_kin.js は URDF の限界を q にそのまま当てているので、実際の角度とずれている。
