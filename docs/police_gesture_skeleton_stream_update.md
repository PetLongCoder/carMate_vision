# 交警手势识别骨骼点与实时识别修改说明

本文记录本轮交警手势识别功能中，Claude 与 Codex 对骨骼点显示、视频叠加同步、摄像头实时识别所做的修改。

## 1. 修改背景

交警手势识别页面原本可以上传视频和打开摄像头进行识别，但缺少可视化骨骼点，排查识别效果时不直观。

后续在加入骨骼点显示后，又陆续出现以下问题：

- 视频模式中，骨骼点比视频画面提前。
- 骨骼点能够显示，但不够贴合人体。
- 摄像头模式中能看到灰色骨骼，但提示未稳定捕获人体。
- 摄像头模式能够捕获人体后，最终稳定动作仍不容易切换出来。

本轮修改围绕这些问题逐步修复。

## 2. Claude 已完成的修改

Claude 主要完成了骨骼点显示能力的初步接入。

### 2.1 后端返回骨骼关键点

在交警手势识别后端推理结果中，增加姿态估计模型输出的 14 个关键点。

关键点来源：

- 姿态估计模型输出 `COORD_NORM`
- 坐标格式为归一化坐标
- 前端按 `[x, y]` 点位绘制

涉及能力：

- 视频上传识别结果可携带逐帧 `keypoints`
- 流式视频分析事件可携带 `keypoints`
- 摄像头实时识别接口可返回当前帧 `keypoints`

### 2.2 前端绘制骨骼覆盖层

在 `frontend/src/pages/PoliceGesture.tsx` 中增加骨骼绘制逻辑。

主要内容：

- 增加 14 个 AI Challenger 人体关键点的骨骼连接关系。
- 在视频预览区域上方叠加 `canvas`。
- 在摄像头实时画面上方叠加 `canvas`。
- 根据后端返回的 `keypoints` 绘制骨骼线和关键点。
- 姿态质量不稳定时，以低透明度/灰色显示骨骼。

这一步让页面能够直观看到姿态估计结果。

## 3. Codex 后续修复

Codex 在 Claude 的骨骼显示基础上，修复了时间同步、坐标映射和实时识别稳定性问题。

### 3.1 修复骨骼点比视频提前

问题原因：

后端为了补偿 LSTM 识别延迟，会对手势标签时间做提前显示，即使用 `label_offset_seconds` 将 `time` 往前挪。

这个补偿适合动作标签和时间线，但骨骼点代表当前帧姿态，不应该跟随补偿后的标签时间。

修复方式：

- 保留后端返回的 `raw_time`。
- 前端标签和时间线继续使用补偿后的 `time`。
- 前端骨骼绘制改用未补偿的 `raw_time/rawTime` 对齐视频帧。
- 绘制循环使用 `requestVideoFrameCallback`，优先按浏览器当前展示的视频帧时间绘制。

涉及文件：

- `frontend/src/pages/PoliceGesture.tsx`
- `frontend/src/store/policeGestureStore.ts`

### 3.2 修复骨骼点不贴合人体

问题原因：

后端在推理前会将原视频帧等比缩放并居中填充到 `512x512` 画布。

姿态模型输出的归一化坐标是基于这个 `512x512` 推理画布的坐标，其中包含 padding。前端如果直接把这些坐标按原视频宽高绘制，就会出现骨骼偏移或拉伸。

修复方式：

- 后端新增 `unletterbox_keypoints`。
- 将关键点从 `512x512` 推理画布坐标还原到原始帧坐标。
- 只对返回前端绘制用的 `keypoints` 做还原。
- LSTM 识别仍使用原模型输入坐标，不影响原有模型推理。

同时，前端绘制时考虑 `<video>` 的真实显示区域：

- 普通视频通常按完整宽高显示。
- 摄像头画面使用 `object-fit: cover` 时可能裁剪上下或左右。
- `drawSkeleton` 根据实际视频显示区域映射坐标，避免骨骼与画面裁剪区域错位。

涉及文件：

- `backend/app/services/police_gesture_service.py`
- `frontend/src/pages/PoliceGesture.tsx`

### 3.3 修复摄像头提示未稳定捕获人体

问题原因：

摄像头实时识别中，后端 `_coord_pose_quality` 用于判断人体姿态是否有效。

姿态模型输出实际格式为 `(2, 14)`：

- 第 1 行是所有点的 x
- 第 2 行是所有点的 y

但原质量评估逻辑把它当作 `(14, 2)` 使用，导致只统计到 2 个点，`validUpperKeypoints >= 4` 永远无法满足。

结果：

- 骨骼能够显示。
- 但 `validPose=false`。
- LSTM 状态不会更新。
- 页面一直提示未稳定捕获人体。

修复方式：

- `_coord_pose_quality` 同时兼容 `(2, 14)` 和 `(14, 2)` 两种格式。
- 对 `(2, 14)` 先转置为 `(14, 2)` 再统计有效点。
- 修复后能够正确统计上半身关键点和手臂关键点。

涉及文件：

- `backend/app/services/police_gesture_service.py`

### 3.4 优化摄像头实时动作稳定输出

问题现象：

人体已经能稳定捕获，但最终动作标签仍经常停留在“无手势”。

原因分析：

- 实时摄像头输入比上传视频更抖动。
- 原实时流要求非 0 手势置信度达到 `0.32` 才参与平滑。
- 9 分类 LSTM 在摄像头场景中置信度可能偏低。
- “无手势”帧容易在平滑投票中压住有效手势。

修复方式：

- 将实时流默认动作阈值从 `0.32` 调整为 `0.18`。
- 平滑投票优先使用可信的非 0 动作。
- 如果窗口内没有可信动作，再回退到无手势。
- 保留 `STREAM_SWITCH_MIN_FRAMES=2`，避免单帧误判立刻切换最终结果。

涉及文件：

- `backend/app/services/police_gesture_service.py`

### 3.5 增加实时识别调试信息

为了区分“模型没有识别动作”和“平滑层没有放行动作”，前端实时结果面板新增了 3 个调试字段：

- `Raw`：LSTM 原始输出。
- `Proposed`：平滑窗口提出的候选输出。
- `Single`：预热阶段单帧辅助模型输出。

观察方式：

- 如果 `Raw` 一直是“无手势”，说明模型对当前摄像头输入不敏感。
- 如果 `Raw` 有动作但 `Proposed` 是“无手势”，说明平滑/阈值仍然偏严。
- 如果 `Proposed` 有动作但最终标签没切换，说明稳定切换帧数或状态保持逻辑需要继续调整。

涉及文件：

- `frontend/src/pages/PoliceGesture.tsx`
- `frontend/src/store/policeGestureStore.ts`

## 4. 当前核心文件

本轮已提交到 `origin/main` 的核心文件：

- `backend/app/services/police_gesture_service.py`
- `frontend/src/pages/PoliceGesture.tsx`
- `frontend/src/store/policeGestureStore.ts`

提交信息：

```text
fix police gesture skeleton overlay and stream recognition
```

提交号：

```text
f3dfbe9
```

## 5. 验证记录

已执行过的检查：

```bash
python -m py_compile backend\app\services\police_gesture_service.py
cmd /c npm run build
```

验证结果：

- 后端 Python 文件语法检查通过。
- 前端 TypeScript 与 Vite 构建通过。
- Vite 构建仍提示 chunk 超过 500 kB，这是项目已有体积警告，与本轮功能修复无关。

## 6. 使用与排查建议

### 6.1 修改后需要重启后端

本轮修改包含后端 Python 推理服务代码。

如果后端不是热重载模式，需要重启后端服务后再测试：

```bash
start_backend.bat
```

或使用项目原本的后端启动方式。

### 6.2 摄像头测试建议

摄像头实时识别依赖连续帧时序。

建议测试方式：

- 人体尽量完整进入画面。
- 上半身、双肩、双肘、双腕尽量清晰。
- 打开摄像头后等待约 3 秒，让 LSTM 完成预热。
- 手势动作幅度尽量明显。
- 优先观察 `Raw / Proposed / Single` 三项，判断问题出在模型输出还是稳定层。



