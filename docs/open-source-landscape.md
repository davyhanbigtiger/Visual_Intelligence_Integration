# 开源方案调研:理解引擎 / 感知层 / 异常检测(草案 v0.1)

> 状态:已联网核实(2026-09-28)。按 [project-goals.md](project-goals.md) 的
> 分层架构(感知层 / 理解层 / 异常判断层 / 整合层)组织,只记录**已核实**的
> license、star数、能力描述,评估性结论会标注"待验证"。这是候选清单,不是
> 选型决定——具体选型要等 Stage 1 架构方案对比阶段再拍板。

## 总览表

| 层级 | 候选 | License | 规模/部署形态 | 与我们硬件的契合度 |
|---|---|---|---|---|
| 理解层(旗舰/云端) | Qwen3-VL-235B-A22B | Apache-2.0 | MoE,235B总参/22B激活,原生支持2小时视频 | 太大,只能上云GPU |
| 理解层(轻量/端侧) | MiniCPM-V 4.6 | Apache-2.0 | 支持 GGUF/llama.cpp,专为手机/边缘优化 | **强契合**:本地CPU + 手机都能跑 |
| 理解层(轻量/端侧) | Molmo2(4B/8B/7B-O) | Apache-2.0 | 权重+数据+代码全开源,支持视频QA/定位/追踪 | 8B以下可本地/单卡跑,待实测 |
| 感知层(检测/追踪) | YOLO26(Ultralytics) | **AGPL-3.0**(需注意) | 边缘优化,CPU ONNX比YOLO11n快43% | **强契合**,但许可证有条件 |
| 异常判断层 | AnyAnomaly(WACV 2026) | 开源代码 | zero-shot,基于LVLM,可定制 | 依赖已选的理解层VLM |
| 异常判断层 | CoReVAD | 开源代码 | training-free,单一冻结VLM | 同上 |
| 整合/RAG框架 | Video-RAG(NeurIPS 2025官方实现) | 开源 | training-free,可挂载任意LVLM | 直接对应"统一理解引擎"设计 |
| 整合/RAG框架 | video-corpus-rag | Apache-2.0 | 全开源组件,含Web UI | 项目较新/较小,需实地验证 |

## 1. 理解层(核心目标所在,详见 project-goals.md §3)

### Qwen3-VL(阿里通义千问)—— 当前最强开源视频理解模型,但太大

- 旗舰版 **Qwen3-VL-235B-A22B**(Instruct + Thinking 双变体),Apache-2.0协议,
  原生 256K 上下文(可扩展到1M),原生支持最长 **2小时视频**理解,32种语言OCR
- 评测直逼 Gemini-2.5-Pro / GPT-5 级别的闭源模型
- 还有较小的 **30B-A3B** 版本(同样是 MoE,激活参数更小)
- **结论**:能力最强,但即便是"激活参数"版本依然需要多卡GPU才能跑,只适合
  作为**云端GPU候选**,不适合本地/边缘部署。是否要用,取决于我们是否愿意
  为"最强理解质量"承担云端GPU成本——这是后续方案对比阶段要权衡的点。

### MiniCPM-V 4.6(OpenBMB,面壁智能)—— 目前看和我们硬件最契合的选项

- GitHub `OpenBMB/MiniCPM-V`,**Apache-2.0**协议,**26.4k star**,项目成熟、
  活跃度高
- 定位就是"**口袋大小的MLLM,专为手机上的图像/视频理解优化**"
- 明确支持 **llama.cpp / GGUF量化**部署,多个量化版本可选
- 同系列 MiniCPM-o 4.5 甚至能做**实时连续视频+音频流**输入,同时输出文本+语音
- **结论**:目前是本项目"本地/端侧理解层"最直接的候选——能在我们这台无独立
  显卡的 Win11 上通过 GGUF/CPU 跑,也有面向手机的部署路径,和硬件清单里的
  约束(见 [hardware-inventory.md](hardware-inventory.md))高度吻合。

**实测结果(2026-09-28,spike,通过 Ollama 本地跑通)**:

- 环境:这台无独立显卡的 Win11 机器,通过 Ollama 拉取 `minicpm-v4.6`(纯CPU推理)
- 测试输入:PC 摄像头拍的一帧真实画面(人物+室内场景)
- **速度**:单张图片、纯CPU推理耗时约 **32.6秒**。这离"亚秒级"很远,但符合
  预期——project-goals.md §5 已经确认 Stage 1 不要求实时,这个速度对"离线
  处理视频文件"是可以接受的(压缩延迟是未来阶段的事)。
- **质量**:输出内容具体、连贯,正确描述了人物、眼镜、衣服颜色、室内场景、
  家具摆件、光线,并且主动指出了一个真实存在的细节(眼镜镜片颜色异常)
  作为"值得注意"的点——不是空泛套话,说明基础理解能力是有的。
- **发现的技术问题(需要在正式接入时处理)**:模型默认返回的内容里混杂了
  一段"思考过程"(reasoning trace)和一个格式不完整的 `</think>` 标签泄漏到
  最终输出里。这与调研时看到的提示一致("运行 Instruct 推理时应显式传
  `--reasoning off`")——正式集成时需要显式关闭/过滤这段内容,不能直接把
  原始 API 输出当作最终字幕/回答使用。
- **结论**:可行性验证通过,MiniCPM-V 4.6 可以作为 Stage 1 理解引擎的起点。
  测试脚本本身是一次性验证脚本(spike 产物),Stage 1 正式实现时需要重新
  设计成结构化的管线代码,而不是直接复用这个脚本。

### Molmo2(Ai2,艾伦人工智能研究院)—— 完全开放,附带定位/追踪能力

- `allenai/Molmo2-8B` 等,**Apache-2.0**,权重、训练数据、代码**全部开源**
  (这在多模态大模型里比较少见,大多数"开源"模型只放权重不放数据)
- 支持图像/多图/视频问答、密集字幕、**指向定位(pointing)、跨帧持续物体
  追踪**——这几项能力正好横跨我们"感知层"和"理解层"的边界
- 提供 4B(效率优先)、8B(通用图像/短视频最强)、7B-O(基于OLMo、追求
  完全开放的研究选择)三个体量
- **结论**:值得重点关注,尤其是它的"追踪+理解"一体化能力,可能能简化我们
  "感知层→理解层"的分层设计(不一定需要两个独立模型)。8B以下体量待实测
  能否在我们本地环境/单张云端GPU上流畅跑。

### 轻量字幕生成配套工具(直接可用的开源小工具)

- **qwen3vl-captioner**(`GitDonkeyHubbed/qwen3vl-captioner`):基于 Qwen3-VL
  GGUF 量化版(如8B)的便携GUI应用,用 llama-cpp-python 跑,下载模型后完全
  离线、不需要云端API
- **JoyCaption**(`1038lab/ComfyUI-JoyCaption`):基于 LLaVA 的 ComfyUI 节点,
  支持批量处理和 GGUF 模型

## 2. 感知层(检测与追踪,project-goals.md §3 中的"眼睛")

### YOLO26(Ultralytics)—— 技术上最契合,但许可证需要注意

- 2026年1月发布,**专为边缘实时部署设计**:NMS-free推理、轻量检测头、
  可预测延迟
- 在 COCO 上五个尺度达到 40.9–57.5 mAP,T4 TensorRT延迟 1.7–11.8ms;
  **CPU ONNX 推理速度比 YOLO11n 快 43%**(Intel Xeon CPU 实测)—— 这一点
  和我们"开发机只有 Iris Xe 核显、无独立GPU"的现状直接相关,值得重点关注
- **License 是 AGPL-3.0**,且已核实清楚条款:如果我们把它整合进一个**对外
  分发或作为网络服务提供**的产品里,AGPL-3.0 要求**公开整个衍生作品的完整
  源代码**(包括我们自己的应用代码、配置、模型权重)。如果不想开源整个项目,
  需要向 Ultralytics 购买 Enterprise License。
  - **结论**:当前阶段(研究/demo,不对外分发/不提供网络服务)使用 AGPL-3.0
    没有问题。但如果本项目未来往"具体应用产品"方向走(project-goals.md §2
    提到的双重定位之一),需要提前规划:要么这部分保持开源,要么预算
    Enterprise License,要么评估 Apache-2.0/MIT 协议的替代检测模型
    (如 RT-DETR 等,**尚未核实**,后续需要单独评估)。这是一个需要写进
    风险清单、而不能等到快要发布产品才想起来的点。
  - **2026-09-28 更新**:本项目 GitHub 仓库(`davyhanbigtiger/Visual_Intelligence_Integration`)
    已设为 **Public + Apache-2.0**。这让上面的冲突从"假设情形"变成了这个
    具体仓库要面对的真实问题:如果以后把 YOLO26 代码接入并随仓库公开分发,
    AGPL-3.0 的强著佐权条款会要求**整个仓库**都按 AGPL 条款开放,而不只是
    YOLO26 那一部分。做感知层选型时必须正式权衡这一点,不能默认"先用着
    再说"。

## 3. 异常/事件判断层(project-goals.md §3 中"感知与理解之间"的角色)

两个2026年的新研究方向都指向同一个思路:**用视觉语言模型做 zero-shot /
training-free 的异常判断,而不是为每种异常单独训练一个检测器**——这与
[research-decision-models.md](research-decision-models.md) 里提到的"小型
decision model 做门控判断"是两条互补的技术路线,而不是互斥的,后续可以
都纳入方案对比。

- **AnyAnomaly**(WACV 2026 论文,`SkiddieAhn/Paper-AnyAnomaly` 官方实现):
  zero-shot、可定制的视频异常检测,基于 LVLM,不依赖"学习过的正常模式"
- **CoReVAD**(`Muk-00/CoReVA`):training-free 的上下文推理框架,用单个
  冻结(不需要微调)的VLM直接生成异常分数和时间描述
- **awesome-video-anomaly-detection**(`fjchange/awesome-video-anomaly-detection`):
  论文+代码合集仓库,可作为持续参考资源,而不是单一方案

## 4. 整合层:如何用同一个引擎同时支持"自动报告"和"问答"

对应 project-goals.md §7 里用户已确认的"两者都要、共享统一理解引擎"的
设计方向,这两个 RAG 框架直接相关:

### Video-RAG(NeurIPS 2025 官方实现,`Leon1207/Video-RAG-master`)

- 学术论文有正式发表backing(NeurIPS 2025),不是野生项目
- **training-free**,可以挂载到"任意"LVLM上(意味着可以搭配上面选定的
  MiniCPM-V / Molmo2 / Qwen3-VL 中的任何一个作为底座)
- 用 OCR、ASR(语音转文字)、物体检测三类"视觉对齐的辅助文本"做检索增强,
  **全部用开源工具实现,不需要任何商业API**——完全符合 AGENTS.md 第17条
  的成本优先级排序

### video-corpus-rag(`bge3867-ai/video-corpus-rag`)

- **Apache-2.0**协议,功能描述上和我们的需求高度吻合:对整个视频库做自然
  语言提问、语义检索、多模态嵌入、VLM推理、ASR/OCR融合、还带一个现成的
  Web UI
- **需要谨慎对待**:没能核实到 star 数或社区活跃度数据,作者/组织信息有限,
  项目成熟度**未经验证**。按 AGENTS.md 第19/30条,这类信息不全的项目只能
  归为"待考察",不能仅凭功能描述就当作可靠选型——如果后续要用,需要先
  实地跑一遍代码、看提交历史和 issue 情况再决定。

## 5. 下一步建议(不是决定,供方案对比阶段参考)

1. 理解层大概率会是"本地/端侧用 MiniCPM-V 或 Molmo2(小体量)+ 需要更强
   效果时按需调用云端 Qwen3-VL"的混合方案——这和 hardware-inventory.md
   里"本地弱算力+按需云端GPU"的资源现实完全对应。
2. 感知层 YOLO26 技术上很合适,但 AGPL-3.0 的产品化影响需要提前写进风险
   清单,不要等到后期才发现。
3. 异常判断层可以先用"VLM zero-shot判断"(AnyAnomaly/CoReVAD思路)加上
   [research-decision-models.md](research-decision-models.md) 里的小型
   decision model 做双重验证/快速门控,两条线都在候选池里,不急于二选一。
4. 整合层优先看 Video-RAG(有论文backing,training-free,不挑底座模型),
   video-corpus-rag 作为"如果懒得自己搭,看看现成方案是否够用"的备选,
   但用之前必须先验证其真实成熟度。
