# VisualIntelligence

一个实时视觉理解研究/demo项目:目标是像人眼配合大脑一样,理解摄像头/视频
看到的真实世界内容和含义,而不只是识别画面里"有什么"。

> 项目目前处于 brainstorming/设计阶段,尚未开始写代码。以下文档记录当前
> 已确认的目标、约束和调研成果,会随讨论持续更新。

## 文档索引

- [docs/project-goals.md](docs/project-goals.md) —— 项目目标、任务定义、场景范围、阶段划分、待决问题
- [docs/hardware-inventory.md](docs/hardware-inventory.md) —— 硬件清单(开发机、手机、云端GPU选项)
- [docs/research-decision-models.md](docs/research-decision-models.md) —— "Decision Model / System One Model" 技术调研笔记
- [docs/open-source-landscape.md](docs/open-source-landscape.md) —— 理解层/感知层/异常检测/RAG整合层的开源方案候选清单,含 MiniCPM-V 4.6 实测结果
- [docs/superpowers/specs/2026-09-28-stage1-video-understanding-design.md](docs/superpowers/specs/2026-09-28-stage1-video-understanding-design.md) —— Stage 1 正式设计spec(已批准,待写实现计划)
- [docs/long-term-roadmap-robot-control.md](docs/long-term-roadmap-robot-control.md) —— 长期北极星:从视频理解到机器人闭环控制的分阶段安全路线图(方向性文档,非当前实现范围)

## 当前状态

- [x] 明确项目北极星目标与场景范围(含情境判断/行动建议、无障碍出行场景)
- [x] 明确 Stage 1 范围:离线处理已提供的视频文件,不涉及实时摄像头
- [x] 完成架构方案对比,选定方案A(VLM-only,MiniCPM-V 4.6起步)
- [x] 完成 Stage 1 设计文档(design spec)并确认
- [x] 记录长期方向(机器人闭环控制)及其分阶段安全里程碑
- [ ] 把 Stage 1 spec 拆成具体实现计划
- [ ] 开始 Stage 1 实现
