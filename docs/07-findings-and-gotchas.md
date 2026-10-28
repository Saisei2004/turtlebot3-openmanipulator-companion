# 07. 分かったことと落とし穴

各項目は「症状 → 原因 → 対処」。数値は 2026-10-25〜28 の作業で測ったもの。DDS・ネットワークまわりは [03](03-network-and-dds.md) と [04](04-dds-verification-guide.md)。

## 1. 腕がカクカク動く（OpenCR の通信が 1 秒に 43 回しかできない）

- **症状**: 腕の動きが階段状。`/joint_states` が約 5 Hz（4.9 Hz）、腕の指令の書き込みが約 0.2 秒ごと。
- **原因**:
  - OpenCR は DXL の通信 1 回に時間がかかり、**1 秒に 43〜44 回しか答えられない**。生のシリアルで測ると、要求のあいだの間隔を 0 / 2 / 5 / 10 / 20 ms と変えても、スループットは 43〜44 回/秒のまま（往復の中央値は 23.0 / 20.9 / 17.9 / 12.9 / 2.9 ms）。Python の DynamixelSDK で 4〜340 バイト読んでも、1 回 23 ms。
  - ROBOTIS の純正プラグイン `turtlebot3_manipulation_hardware`（v2.2.1）は、1 周期に**7 回**通信する（心拍、車輪の書き込み、関節の目標、その書き込みフラグ、グリッパーの目標、そのフラグ、制御テーブル全体 344 バイトの読み取り）。機体の上の C++ SDK では 1 回約 28 ms（`strace` で観察）→ 1 周期 約 200 ms。
- **対処**: パッチ（`robot/hardware_patch/tb3_manipulation_hardware_fewer_transactions.patch`、公式 `814f140` に当たる）。
  - 関節 1〜4 とグリッパーの目標・フラグ（制御テーブルの 200〜221 番地、連続している）を **22 バイト 1 回の書き込み**にまとめる。
  - 指令が変わったときだけ書く。読み取りは 100 ms ごと、心拍は 200 ms ごと、車輪の定期の書き直しは 300 ms ごと、腕の定期の書き直しは 400 ms ごと。
  - 腕の書き込みの間隔は 40 ms 以上空ける。読み取り・心拍・車輪の定期の通信は、1 周期に 1 つまで（心拍は 300 ms、車輪は 600 ms を超えたら重なってでも送る）。
  - サーボの加速の上限を 100 → 25、速度の上限を 500 → 300 に（環境変数 `TB3_JOINTS_PROFILE_ACCELERATION` / `_VELOCITY`、`tb3.env` の値）。指令と指令のあいだがなめらかにつながる。
- **結果（実機）**: 腕の目標の書き込みは、最初のパッチで中央値 32 ms（途中で 60〜115 ms に延びる）。間隔をそろえたあとは、中央値 58 ms、40〜60 ms に収まる割合が **53% → 80%**、最大 104 → 86 ms。
- **戻すには**（機体の `~/REVERT_HW_PATCH.txt` と同じ）:

  ```bash
  sudo systemctl stop tb3-bringup
  rm -rf ~/turtlebot3_ws/src/turtlebot3_manipulation_hardware ~/turtlebot3_ws/build/turtlebot3_manipulation_hardware ~/turtlebot3_ws/install/turtlebot3_manipulation_hardware
  sudo systemctl start tb3-bringup
  ```

- 道具: `tools/time_reads.py`（DynamixelSDK での 1 回の時間）、`tools/raw_latency2.py`（生のシリアルでの往復と、間隔を変えたスループット）。どちらも `tb3-bringup` を止めてから動かす（ポートの取り合い）。

## 2. 腕の指令の出し方で、なめらかさが変わる

- **症状**: 手先操作・Dance で、動きに細かい乱れ。コントローラの指令速度に 1.89 rad/s のとげ（大きさ 0.6 の Dance）。
- **原因**: 0.15 秒先の 1 点だけの軌道を 20 Hz で出し直すと、コントローラが毎回、軌道を組み直す。
- **対処**:
  - 手先操作: 先 0.2 秒・0.4 秒の 2 点（速度つき）を 20 Hz。
  - Dance: 先 1.5 秒（0.1 秒ごと 15 点、速度つき）を 0.5 秒ごと。連続する塊の重なりの位置のずれは 0.0001 rad。
  - 止まる仕組みは、機体側の見張りに任せる（[06](06-safety.md)）。
- **結果（実機）**: コントローラの指令位置の速度の最大 0.57〜0.84 rad/s（計画は約 0.5 rad/s、0.6 倍で動かしたとき）。実際の関節は、指令に **0.2〜0.3 秒**遅れて付き、位置のずれは平均 0.003〜0.023 rad、最大 0.06 rad。
- 注意: `/joint_states` は約 75 回/秒出るが、新しい値は 10 回/秒（読み取りが 100 ms ごと）。画面の側面図は、`/arm_controller/controller_state` の `reference`（コントローラが今出している指令位置）で描く。

## 3. 関節の 0 位置が URDF とずれている / 旧 home が自己衝突する

[05](05-arm-kinematics-and-mujoco.md)。要点: `a = q + OFFSET`、`OFFSET = [0, 0.93, 0.07, -1.65]`。旧構成の home（`q = [-0.0199, -0.813, 1.5142, 0.0337]`）は joint3 が限界を超え、`link2` と `link4` が約 23.5 mm めり込む。HOME は `q = [0, -1.98, 0.98, 1.65]`。

READY を指令しても、joint3 は指令 -0.07 に対して実測 -0.038 のように、0.03 rad ほどずれて止まる（重力・バックラッシュと推測）。

## 4. 電池切れで、制御が動かなくなる

- **症状**: 画面から何も効かない。`journalctl -u tb3-bringup` に `Can't control joints` / `Can't control wheels` / `Can't control gripper`、`Failed to read all control table`、`There is no status packet!`。`ros2_control_node` と LiDAR のプロセスは動き続けている。
- **原因**: 電池が減って、モーターの電源が落ちた。OpenCR の通信は生きているが、ros2_control は復帰しない。
- **対処**: 充電してから、`tb3-bringup` を起動し直す。

  ```bash
  sudo systemctl restart tb3-bringup
  ```

  自動化: `tb3-watchdog`（ログの `Can't control (joints|wheels)` を見て再起動、60 秒に 1 回まで）と、udev の `98-tb3-opencr-restart.rules`（OpenCR が USB でつなぎ直されたとき）。停止直後の電圧は 11.06 V（約 32%）。
- 電圧は ROS のトピックに出ていない。`tb3-bringup` を止めて `tools/read_battery.py`（OpenCR の制御テーブル 42 番地、100 倍の整数）。
- 最初は「OpenCR が USB から切れた」と誤診した。`dmesg` の USB 切断の記録は、ファームウェアを書き込んだときのものだった。

## 5. OpenCR が、ポートを開いた直後は答えない

- **症状**: ポートを開いてすぐ問い合わせると `There is no status packet!`。
- **原因**: ポートを開くと OpenCR が 0.5 秒ほど応答しない（測定: 0.0 秒後は失敗、0.5 秒後に成功）。
- **対処**: 開いてから 1.5〜2 秒待つ（`tools/` のスクリプトはそうしている）。起動直後のログに `no status packet` が 1 回出るのは、この影響（無害）。

## 6. LiDAR のドライバ

- **症状**: LDS-01 用のドライバ（`hlds_laser_publisher`）で `/scan` の距離が全部 0。
- **原因**: この機体は LDS-02。旧 SD には LDS-01 用のドライバしかなく、旧構成では LiDAR が動いていなかったのかもしれない（推測）。
- **対処**: `ld08_driver`（`LDS_MODEL=LDS-02`）。`tools/try_lds.sh` で両方試せる（機体の上で、`tb3-bringup` を止めて）。

## 7. ROS_DOMAIN_ID

e-Manual の既定は 30。この機体は旧構成に合わせて **0**。PC と機体で同じにする。

## 8. WSL / Windows の落とし穴

| 症状 | 原因 | 対処 |
|---|---|---|
| `wsl.exe -d X -- bash -c '... $VAR ...'` で変数や `;` が壊れる | `--` の後ろは Windows 側のシェルを通る | **`wsl.exe --exec`** で、引数をそのまま渡す（`tb3ctl` はそうしている） |
| `config/tb3.env` を読むと `$'\r': command not found` | Windows が改行を CRLF で書いた | `tb3ctl init` は LF で書く。`tb3_config.sh` は `tr -d '\r'` を通して読む |
| サーバーを起動し直すと rosbridge が `Unable to start server: [Errno 98] Address already in use` を繰り返す | `tb3_server.py` だけを落とす・端末の窓を閉じると、古い `rosbridge_websocket` が 9090 を持ったまま残る | `tb3ctl stop`（`pc/scripts/kill_server.sh`）。起動のたびに自動でも呼ぶ |
| `kill_server.sh` が、呼び出し元の `start_server.sh` を殺す | `pkill -f start_server.sh` が自分の親にも当たる | 自分と親のプロセス番号を除いて殺す（直した） |
| 動いているシェルスクリプトを書き換えると `XIT: command not found` | bash は、スクリプトを読みながら実行する | 動いているあいだは書き換えない |
| 機体から PC に ROS 2 の通信が届かない | Hyper-V ファイアウォールが、WSL への外からの受信を既定で全部止める | 管理者の PowerShell で `pc/scripts/windows/allow_wsl_ros2_firewall.ps1`（[01](01-quickstart-new-pc.md)） |
| `.wslconfig` を書いても mirrored にならない | `wsl --shutdown` が要る | 落として、もう一度起動する |
| `ssh -o HostName=<別の IP> <別名>` で、ホスト鍵のエラー（`Host key verification failed`） | `known_hosts` のキーが、元の IP / 名前で入っている | `-o HostKeyAlias=<元の名前>` を付けるか、`-o StrictHostKeyChecking=accept-new` で新しい IP を登録する（`tb3ctl` は `accept-new` を付けている） |
| WSL と Git Bash で `/tmp` が違う | 別のファイルシステム | WSL に渡すファイルは、リポジトリの中（`/mnt/<ドライブ>/...`）に置く |
| `ros2 topic hz` / `echo` が何も出さない | 発見が終わっていない（最初の 1 つは特に）。`ros2 daemon` が古い発見の結果を持っている | `ros2 daemon stop`。`--no-daemon` を付ける。時間を長めに取る。測定ツールは `dds/tools/` |

## 9. Windows の ICMP は、機体 → PC が届かない

- **症状**: 機体から PC への `ping` が 100% 損失。PC から機体への `ping` は 60/60（平均 6 ms、最大 30 ms）。
- **原因**: Windows のファイアウォールが、PC への ICMP echo の受信を止める（DDS の UDP は、別の規則で通している）。
- **対処**: 機体から PC への疎通は `ping` で見ない。ROS 2 のトピックで見る（`tb3ctl status` の `link_ok`）。

## 10. ブラウザの roslib 1.4.1 は、ROS 2 のアクションを扱えない

- **症状**: 画面のスクリプトが `ROSLIB.Action is not a constructor` で止まる。
- **対処**: グリッパーは、rosbridge のメッセージを直接送る: `ros.callOnConnection({op: "send_action_goal", id, action: "/gripper_controller/gripper_cmd", action_type: "control_msgs/action/GripperCommand", args: {command: {position, max_effort: -1.0}}, feedback: false})`。rosbridge は、アクションの目標を別のスレッドで処理する設定（`send_action_goals_in_new_thread:=true`）で起動する（走行の停止が、グリッパーの完了待ちで止まらないように）。

## 11. 画像・カメラまわり

- **HEIC（iPhone の写真）**: `ffmpeg` では、写真が 512×512 のタイルに割れて出る。Windows の WIC で読む（PowerShell の `System.Windows.Media.Imaging.BitmapDecoder`）。
- **ウェブカメラ**: この PC の `HD Webcam eMeet C960` を、`ffmpeg -f dshow -video_size 1920x1080 -i video="HD Webcam eMeet C960" -ss 3 -frames:v 1 ...` で 1 枚撮った。最初のフレームは暗い・露出が合っていないので、`-ss 3` で待つ。部屋が暗いと `eq=brightness=0.08:contrast=1.3:gamma=1.6` で明るくした。作業の途中で、カメラが見えなくなった。リポジトリには、このための道具を入れていない。腕の姿勢の実測（[05](05-arm-kinematics-and-mujoco.md)）はこれでやった。

## 12. SD カード（Mac）

- Mac では、SD の起動領域（`system-boot`）は、ssh 越しだと `Operation not permitted`（リムーバブルボリュームの保護）。ターミナルアプリで、本人がスクリプトを動かす。
- この PC の Windows は、SD カードリーダーを認識しなかった（Mac の外付けリーダーでは認識）。

## 13. 試験の道具（`tools/`、機体の上で動かすもの）

| ファイル | 内容 | 注意 |
|---|---|---|
| `time_reads.py` / `raw_latency2.py` / `probe_opencr.py` / `read_battery.py` | OpenCR との通信の測定・読み取り | `tb3-bringup` を止めてから |
| `record_ref.py` / `record_stream2.py` | 指令位置の速度・追従・心拍の間隔・PC が止まってから腕が止まるまでを記録 | 機体の上で。`ROS_DOMAIN_ID` と DDS の環境を `/etc/tb3/env.sh` と同じにする |
| `nudge_joint.py` | 関節を 1 つだけ少し動かす | **腕が動く** |
| `wheel_test2.py` | 0.05 m/s で約 2 秒前進して、車輪の角度が変わるか | **車輪が動く**（実測で両輪とも約 2.3 rad、約 8 cm 進む） |
| `try_manip.sh` / `try_lds.sh` | 制御・LiDAR ドライバを試しに起動 | `ROS_DOMAIN_ID=77` で動かす。`tb3-bringup` と二重に動かさない。`try_manip.sh` は `LDS_MODEL=LDS-01` のまま（古い） |
