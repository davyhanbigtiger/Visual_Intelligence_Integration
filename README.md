# VisualIntelligence

一个实时视觉理解研究/demo项目:目标是像人眼配合大脑一样,理解摄像头/视频
看到的真实世界内容和含义,而不只是识别画面里"有什么"。

> 项目目前处于 brainstorming/设计阶段,尚未开始写代码。以下文档记录当前
> 已确认的目标、约束和调研成果,会随讨论持续更新。

## 文档索引

- [docs/project-goals.md](docs/project-goals.md) —— 项目目标、任务定义、场景范围、阶段划分、待决问题
- [docs/hardware-inventory.md](docs/hardware-inventory.md) —— 硬件清单(开发机、手机、云端GPU选项)
- [docs/research-decision-models.md](docs/research-decision-models.md) —— "Decision Model / System One Model" 技术调研笔记
- [docs/open-source-landscape.md](docs/open-source-landscape.md) —— 理解层/感知层/异常检测/RAG整合层的开源方案候选清单

## 当前状态

- [x] 明确项目北极星目标与场景范围
- [x] 明确 Stage 1 范围:离线处理已提供的视频文件,不涉及实时摄像头
- [ ] 完成架构方案对比(2-3个候选方案 + 取舍)
- [ ] 完成设计文档(design spec)并确认
- [ ] 开始 Stage 1 实现
