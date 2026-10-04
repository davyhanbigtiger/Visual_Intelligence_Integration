# VisualIntelligence

一个实时视觉理解研究/demo项目:目标是像人眼配合大脑一样,理解摄像头/视频
看到的真实世界内容和含义,而不只是识别画面里"有什么"。

> Stage 1 离线视频理解已实现：支持视频报告与问答。自动化测试已通过；
> 真实场景理解与导航建议的质量仍需按设计文档逐项验收。

> 2026-10-02 状态更新：已增加 Windows 11 摄像头 demo；本机摄像头读取、
> 预览 smoke test 和一次真实模型调用已验证，87 项测试通过。连续场景质量仍待验收。
> 详见 [当前项目状态](docs/project-status-2026-10-02.md)。

## 当前研究目标：本地算力 ↔ 远程 GPU 的最低成本平衡点（2026-10-03）

> 用户原话：能在 GPU 高性能计算机的远程支持和当地的 CPU 或者小型 GPU 计算力之间，
> 找到一个最低价格、最有效策略的平衡点——远程 GPU 在实际应用场景会遇到图片和视频
> 传输速度的影响，而把 GPU 本地化，对产品价格的影响也很高。

**做法**：把它写成可检验的问题——在延迟、断网可用性、隐私、云服务月预算（≤ 100 加元，
仅作调研约束，不是购买授权）等约束下，最小化 `本地硬件摊销 + 云端月费 + 流量费`。
**暂定方向（待实验验证，不是结论）**：本地常驻轻量层（门控 + 断网兜底）+ 云端按需增强，
上传关键帧而不是视频流；手机端侧 NPU 是零边际硬件成本的候选，但还没在你的设备上实测。
目标定义、证据清单（实测 / 官方页面 / 厂商声称 / 待测）和工作计划见
[目标文档](docs/cost-balance-target-2026-10-03.md)；成本与流量模型见
`scripts/cost_model.py`。

**长期规则（AGENTS.md 第 31 条，2026-10-03）**：每次 benchmark 都必须附“最优性审计表”——
回答本地方案是否已找不到更优解、当前模型是不是最优、有没有其他模型、参数/配置是否调到最优、
有没有更好的方式；没有审计表不得声称“最优/最快”，最强说法只能是“在已列出的已测配置中最优”。

**同日补充的第二条目标——本地方案“极致化”审计**：当前模型和本地配置是否已经调到最优、
最快，本地方案本身是不是最好？这决定本地层能挡掉多少云调用。审计清单（输入尺寸/分块数、
线程、请求形式、缓存、引擎：Ollama CPU vs llama.cpp CPU vs 核显 SYCL、并发、OpenVINO、
更小模型、量化）及每项状态见目标文档第 8 节。**已发现并更正一处会影响结论的旧错误**：
早先“核显路径没有明显优于 CPU”所用的 CPU 基线（约 4.5 秒）是缩图/缓存命中的数字，
真实新图 640×480 在 Ollama 默认配置下约 16.8 秒。**受控对照已完成**（同一 llama.cpp、同一 GGUF、
同一批帧，n=12/档，详见[延迟分布文档](docs/latency-distribution-2026-10-03.md)）：
Iris Xe 核显（SYCL）比同引擎 CPU 快 2.1×（640）/1.7×（448），640 档 6.5 秒、448 档 3.0 秒；
生产用的 Ollama 只加环境变量 `OLLAMA_IGPU_ENABLE=1` 就能走 Vulkan 核显，640 档 7.3 秒、448 档
4.9 秒（比 Ollama CPU 快 2.3×/1.6×），**但在 24 张公开 COCO 图的冒烟运行里有 3 个输出变成坐标乱码、
不是合法 JSON，同样的请求在 CPU 上 6/6 合法**——云 T4 上 Ollama 并发时也出现过同样的乱码，而 llama.cpp 在
271 个请求里 0 个，所以问题在 Ollama 的运行器路径上，根因未确认，查清前不建议默认启用；产品里应校验 JSON 并失败重发。
448 以下只切一块图（快约 2.2×）但“无依据物体断言”增多。
结论强度：单机、单次会话、内存紧张未受控；“已找不到更优解”**不成立**（OpenVINO、并发、
llama.cpp 参数、更多模型等仍未穷尽）。默认行为本轮未改。

**云 GPU（腾讯云东京 Tesla T4，1.54 元/小时）已实测（2026-10-04）**：MiniCPM-V 4.6 端到端约 1 秒
（llama.cpp 640 档 0.96 秒、448 档 0.72 秒；Ollama 1.23 / 0.98 秒；含约 0.4 秒跨洋往返，往返才是主要瓶颈），比本机核显
快约 4.8–7 倍；24 小时常驻约 236 加元/月，超出 100 加元预算，只有每天超过约 1.1 万次事件才比 Gemini Flash-Lite
按次计费便宜。详见 [T4 实测与审计](docs/cloud-t4-results-2026-10-04.md)；测试流程见
[云 GPU 测试手册](docs/cloud-gpu-test-runbook-2026-10-03.md)（只用公开/合成媒体，没有上传摄像头画面或个人录像）。

## 本地运行（Windows PowerShell）

当前优先目标是**环境概况与低延迟**：识别大致场景、主要人物、显眼物体和
姿态即可，不要求识别杯中饮品等隐藏细节；导航建议暂不作为该目标的验收条件。
模型决策（2026-09-30）：保留 MiniCPM-V 4.6 / Ollama 为默认；SmolVLM-500M
CPU 作为未来 Plan B 或辅助模型候选，尚未接入自动切换或辅助流程。
简短模式只处理一个时刻，默认视频中间一帧：

```powershell
.venv\Scripts\python -m visualintel scene videos/test_video.avi
.venv\Scripts\python -m visualintel scene videos/test_video.avi --at 8
```

`scene` 输出采样时间及一两句环境概况，不生成异常或建议字段；模型输出
上限为 96 tokens。它不是整段视频摘要，可能遗漏其他时刻出现的物体或事件。
既有 `report`/`ask` 保留用于需要多帧理解的任务。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
ollama list
# 仅在模型尚未安装时运行：ollama pull minicpm-v4.6
.venv\Scripts\python -m visualintel report videos/test_video.avi
.venv\Scripts\python -m visualintel ask videos/test_video.avi "画面中的人做了什么？"
.venv\Scripts\python -m pytest -q
```

将已录制视频放入 `videos/`。报告保存到 `outputs/<视频名>/report.json` 与
`report.md`。已有报告不会被覆盖；再次运行请使用新的 `--output-dir`。

`report` 可用 `--max-chunks 20` 设置处理上限，`--workers 1` 至其他正整数
设置并发数（默认 4）。4 路的历史加速数据来自 llama.cpp/SYCL，尚不能当作
Ollama 的性能保证。两种命令均支持 `--model`，默认 `minicpm-v4.6`。
`ask --question-mode factual` 强制只回答事实；`--question-mode advice` 明确
求建议并始终附带免责声明，默认 `auto` 使用关键词判断。

模型调用使用 JSON Schema 限制字段、验证类型和异常标记的一致性；无效或
被 token 上限截断的结构化输出会重试一次，仍失败则记录错误。
输出长度有上限，temperature 设为 0；这些措施改善格式与可控性，不保证
事实准确或建议安全。旧文本响应解析仍保留以便读取此前输出。

退出码：0 成功；1 视频、参数或文件读写错误；2 Ollama/模型未就绪；
3 模型调用或部分 chunk 失败。失败 chunk 仍会写入报告，保留其他结果。

采样默认每 2 秒一帧，每 chunk 最多 8 帧、最多 20 个 chunk；截断会在报告
注明。`ask` 仅均匀抽取最多 8 帧，长视频中的短暂事件可能遗漏。
报告时间范围表示首末采样帧的时间，并不代表持续观察了中间每一帧。
建议语气由 prompt 约束，代码会拦截部分明显指令句，但不能识别所有措辞；
无法保证模型每次遵守。confidence 是模型自评，
不是校准概率。输出仅供事后参考，距离不能视为可靠测量。
问答通过中英文问题关键词区分事实与建议，事实问题会过滤 guidance；
复杂或含糊的问题可能被误判，不能将这一规则当作可靠的语义分类器。

可复现的模型对照工具（原始响应与耗时保存在新的输出目录）：

```powershell
.venv\Scripts\python scripts/evaluate_models.py --model minicpm-v4.6 --output outputs/evaluation-new --improved-prompt
```

评估只记录格式校验结果；理解质量须按原图/视频人工核对。图片缓存、首次
模型加载和帧数都会影响耗时，不能把少量顺序请求当作稳定性能排行榜。

环境概况图片测试可用 `scripts/evaluate_scenes.py`，支持可选
`--max-image-side 640`。Google 找到的三张公开图实测和来源详见
[环境概况评估](docs/environment-awareness-evaluation-2026-09-30.md)。
进一步的320像素对照、SmolVLM实测及OpenVINO/Florence/FastVLM候选见
[延迟选项评估](docs/latency-options-2026-09-30.md)。
已完成500M与OpenVINO CPU/GPU的[追加实测](docs/smolvlm-openvino-evaluation-2026-09-30.md)，
快模式候选仍属实验，未替换默认模型。

## Windows 11 摄像头 demo

在项目目录的 PowerShell 中运行（先确保 Ollama 正在运行）：

```powershell
.venv\Scripts\python -m visualintel camera
```

窗口实时预览；点击“分析当前画面”后，MiniCPM 分析一张最长边 640 像素的帧。
小图显示实际提交帧，文字显示环境概况、耗时及帧的时间差。描述当前使用英文。
可勾选连续分析：完成后等待 2 秒，再采最新帧；始终最多一个请求，不排队。
预览更新不代表模型能逐帧实时理解；首次模型加载、结构校验失败重试会增加耗时。
请求超时为每次 60 秒，最多两次尝试。关闭窗口或按 Esc 释放摄像头；已提交的
Ollama 请求可能仍在服务端完成。默认不保存画面、视频或描述，推理走本机 Ollama。

无法打开时，检查 Windows 设置 → 隐私和安全性 → 摄像头中的桌面应用权限，
关闭占用摄像头的应用；可尝试 `--index 1` 或 `--backend msmf`。
`--max-image-side 320` 可作低分辨率速度对照，但可能损失细节；默认仍为 640。
摄像头 demo 不控制机器人。测试视频和生成报告均被 gitignore。

## 文档索引

- [docs/cost-balance-target-2026-10-03.md](docs/cost-balance-target-2026-10-03.md) —— 目标：本地算力 ↔ 远程 GPU 的最低成本平衡点（目标、约束、证据清单、计划）
- [docs/latency-distribution-2026-10-03.md](docs/latency-distribution-2026-10-03.md) —— 本机延迟受控实测（输入尺寸/分块阈值、CPU vs 核显、Ollama+Vulkan）与最优性审计表
- [docs/cloud-t4-results-2026-10-04.md](docs/cloud-t4-results-2026-10-04.md) —— 云 T4 实测：延迟、并发、冷启动、参数扫描、成本推算、非法输出比较与审计表
- [docs/cloud-gpu-test-runbook-2026-10-03.md](docs/cloud-gpu-test-runbook-2026-10-03.md) —— 云 GPU 短租测试手册：准备物、隐私规则、步骤、测试内容、结束清单
- [docs/project-status-2026-10-02.md](docs/project-status-2026-10-02.md) —— 当前目标、模型决策、摄像头启动与验证限制

- [docs/project-goals.md](docs/project-goals.md) —— 项目目标、任务定义、场景范围、阶段划分、待决问题
- [docs/hardware-inventory.md](docs/hardware-inventory.md) —— 硬件清单(开发机、手机、云端GPU选项)
- [docs/research-decision-models.md](docs/research-decision-models.md) —— "Decision Model / System One Model" 技术调研笔记
- [docs/open-source-landscape.md](docs/open-source-landscape.md) —— 理解层/感知层/异常检测/RAG整合层的开源方案候选清单,含 MiniCPM-V 4.6 实测结果
- [docs/superpowers/specs/2026-09-28-stage1-video-understanding-design.md](docs/superpowers/specs/2026-09-28-stage1-video-understanding-design.md) —— Stage 1 正式设计spec与验证记录
- [docs/superpowers/plans/2026-09-28-stage1-video-understanding-plan.md](docs/superpowers/plans/2026-09-28-stage1-video-understanding-plan.md) —— Stage 1 实现计划与执行状态
- [docs/long-term-roadmap-robot-control.md](docs/long-term-roadmap-robot-control.md) —— 长期北极星:从视频理解到机器人闭环控制的分阶段安全路线图(方向性文档,非当前实现范围)
- [docs/benchmark-matrix.md](docs/benchmark-matrix.md) —— 硬件档位 vs 延迟的能力矩阵(哪个硬件档位能做到多快,持续补充)
- [docs/model-evaluation-2026-09-30.md](docs/model-evaluation-2026-09-30.md) —— 本地模型实测、结构化改进与质量限制

## 当前状态

- [x] 明确项目北极星目标与场景范围(含情境判断/行动建议、无障碍出行场景)
- [x] 实现原 Stage 1 离线范围；后续按用户授权增加独立摄像头 demo
- [x] 完成架构方案对比,选定方案A(VLM-only,MiniCPM-V 4.6起步)
- [x] 完成 Stage 1 设计文档(design spec)并确认
- [x] 记录长期方向(机器人闭环控制)及其分阶段安全里程碑
- [x] 完成 Stage 1 实现计划(9个TDD任务)
- [x] 开始硬件能力矩阵调研(本机CPU数据已实测,GPU档位待补)
- [x] 实现 Stage 1 Python 包、report/ask CLI 与自动化测试
- [x] 实现单帧 scene 与 Windows 11 camera demo；2026-10-02 重新验证 87 项测试通过
- [x] 保留 MiniCPM 默认；SmolVLM-500M CPU 作为未来 Plan B/辅助候选
- [ ] 完成摄像头连续真实场景质量与稳定性验收
- [ ] 完成 Stage 1 真实障碍物视频与人工质量验收
- [ ] 补全硬件矩阵(Iris Xe SYCL / 云GPU 数据点)
- [x] 记录新目标：本地 ↔ 远程 GPU 最低成本平衡点（2026-10-03），含成本/流量模型脚本与官方价格核实
- [ ] 视觉分块阈值实验、摄像头验收、SmolVLM 对比、付费方案调研与决策文档（进行中）
- [ ] 需要用户参与：云 GPU / 托管 API 实测（注册、支付、密钥由用户完成，只用公开图）；iPhone/VIVO 机型与系统版本（手机端侧实测）
