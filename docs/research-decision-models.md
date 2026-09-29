# Decision Models / System One Models —— 调研笔记(草案 v0.1)

> 状态:已联网核实(2026-09-28)。这整个类别是我训练知识截止(2026年1月)
> 之后才出现的新东西,发展非常新(绝大多数项目/文章发布于2026年9月)。
> 按 AGENTS.md 第30条的分类标准,整体归为**"有前景但仍处于实验期
> (Promising but experimental)"**,不是"生产就绪(Production-ready)"。
> 所有结论均标注来源,推断部分明确标出"尚未核实/初步想法"。

## 1. 这类模型是什么

"Decision Model"(也叫"System One Model")是一类专门做**结构化决策**而不是
生成文本的小模型:

- 输入:一个状态 + 一组预先定义好的选项(类似做选择题)
- 输出:每个选项的**校准概率**,单次前向传播完成,没有链式推理/多轮生成
- 优点:极快(几毫秒到几十毫秒,比大模型快约40–200倍)、结果可直接被程序
  消费(不用解析自然语言)、输出被限定在预设选项里,不会"胡言乱语"
- 缺点:不能做多步推理/复杂计算,只适合分类/路由/打分/门控类任务,
  不能替代生成式的字幕/开放问答能力

## 2. 具体项目核实结果

### Jev(TypeSafe AI)—— 这个类别的发起者,但不能直接用

- 2026年9月15日由 TypeSafe AI(前 OpenAI 研究员 Diogo Almeida 创立的旧金山
  创业公司,DCVC 领投4000万美元种子轮)发布
- **纯闭源云端 API 产品**:不开放权重、不能自托管、不能离线运行,目前处于
  邀请制早期访问(waitlist)
- 定价约 $0.042/百万 input token,输出免费(因为输出是结构化决策而非文本)
- **结论**:不符合本项目"本地优先、开源优先"的取舍原则(见
  [project-goals.md](project-goals.md) 及 AGENTS.md 第17条),且当前邀请制,
  拿不到访问权限。可以了解其设计理念,不建议依赖。

### Decision 1.0(vLLM Semantic Router 项目)—— 背书最扎实的开源选项

- 来自 vLLM Semantic Router 项目(`vllm-project/semantic-router`,GitHub
  约4.8k star,**Apache-2.0**协议),依托成熟的 vLLM 生态,不是个人玩票项目
- 包含6个不同大小的开放权重模型:Kai-0.6B、Lex-0.6B、Eos-0.8B、Sol-2B、
  Nox-4B、Lux-9B,覆盖双向编码器和因果解码器架构
- 定位:路由(routing)、策略门控(policy gating)、agent 动作决策、批量决策
- **结论**:license 和项目背书最扎实,但"Decision 1.0"这个具体功能刚合入/
  刚发布,长期维护记录还需要观察时间。

### decider-2b 系列(`Mapika/decider`,作者 Mark Marosi)

- GitHub `Mapika/decider`,**Apache-2.0**协议,约771 star,近期(2026-09-22)
  有 PR 合并,活跃维护中
- 基于 Qwen3.5-2B 微调,社区有多个衍生格式:GGUF 量化版(纯 CPU/无 GPU
  环境可跑,llama.cpp 生态)、`nativ-community/decider-2b` 等镜像(据称约
  4.2万次下载)
- **decider-2b-vision**(图像版,与本项目关系最直接):把 decider-2b 的决策
  能力移植到 Qwen3.5-2B 视觉语言模型上——输入"一张图 + 带选项的问题",
  单次前向输出每个选项的校准概率,显存需求约4GB。**不能生成字幕/自由回答**,
  只能做"选择题式"判断。
  - 存在 **LiteRT**(Google TFLite 生态)版本
    `litert-community/decider-2b-vision-LiteRT` —— 对我们的 **VIVO Android
    手机**是个直接可用的信号(端侧 NPU/移动端推理生态)
  - 存在 **GGUF** 版本 —— 对我们**无独立显卡的 Win11 开发机**是个直接可用
    的信号(纯 CPU 也能跑)
- **结论**:目前看到的、和本项目关系最直接的一个候选。可用于给感知层的
  结构化输出做"是否异常 / 要不要升级到云端理解层"这类门控判断,但项目
  仍很新(不到一个月),建议先小范围试用验证效果,不作为 Stage 1 的强依赖。

### von(`wfzyx/von`)—— 另一个开源本地替代方案

- GitHub `wfzyx/von`,**Apache-2.0**协议,约600+ star,活跃开发中
- 非自回归架构,基于 ModernBERT-Large,延迟约15–25毫秒,定位为 Jev 的
  "本地免费替代品"
- 有 Apple Silicon(MLX)移植版 `IAMIbrahimmemon/von-mlx` —— 对我们的
  iPhone/Mac 生态可关注,但 MLX 目前主要面向 Mac(非 iOS 原生运行时),
  能否直接用于 iPhone 端侧部署**尚未核实**
- 目前看是纯文本决策模型,**没有确认视觉输入版本**,对"视觉理解"场景的
  直接适配度低于 decider-2b-vision

### jeff —— Jev 的开源自托管替代(信息有限)

- **MIT协议**,基于 GLiFormer(400M参数编码器模型),定位为"Jev API 的
  自托管开源平替"
- 参数量比 decider-2b 小(400M vs 2B),可能更适合资源受限场景,但具体
  效果/维护活跃度**尚未单独核实**,列为候选,后续需要时再评估

### ollaya —— 值得关注的配套基础设施(未深入核实)

- `ollaya-dev/ollaya`:定位为"decision models 的 Ollama"——可本地拉取并以
  兼容 TypeSafe API 的方式提供 Laya、decider、NLI、GLiClass 等模型服务
- 如果本项目决定采用某个 decision model,这类工具能省掉自己写推理服务的
  功夫,但**没有核实其 star 数/license/维护活跃度**,后续要用需单独评估

## 3. 对本项目架构的潜在用途(初步想法,尚未定案)

结合 [project-goals.md](project-goals.md) "感知层(检测/追踪)→ 理解层
(字幕/VQA)"的分层设计,decision model 可能适合放在两个位置——**都还没有
定案,需要在后续方案对比阶段正式评估,不是现在就拍板的决定**:

1. **异常/事件判断层的实现方式**:与其手写规则或为"是否异常"单独调用一次
   云端大模型,不如用 decider-2b(-vision)这类小模型,把感知层输出的结构化
   状态喂给它,单次前向拿到"是否异常"的校准概率——本地、CPU 可跑、毫秒级。
2. **理解层的路由门控**:用一个 decision model 先快速判断"这一帧/这段内容
   有没有变化、值不值得触发一次较贵的云端 VLM 字幕/VQA 调用",避免每帧都跑
   重模型,契合 project-goals.md 第3节"字幕按低频/场景变化触发"的方向。

## 4. 需要谨慎对待的地方(AGENTS.md 第30条要求)

- 整个类别(包括所有提到的具体项目)**发布时间都在2026年9月**,还没有经过
  时间考验,分类应归为"有前景但仍处于实验期",不是"生产就绪"。
- Star数、下载量等指标可能受一时热度影响(如 Jev 本身刚获融资、刚上线造势),
  需要再观察几周/几个月的社区反馈,不宜现在就下重注。
- 建议:Stage 1 设计阶段把 decider-2b-vision 列为"候选评估对象"之一,但不
  现在就绑定依赖;等 Stage 1 的理解引擎基本框架跑通后,再单独做一次小实验
  验证它在我们场景下的实际效果。

## 参考来源

- [Hugging Models on X: Meet decider-2b](https://x.com/HuggingModels/status/2102192408100487590)
- [nativ-community/decider-2b · Hugging Face](https://huggingface.co/nativ-community/decider-2b)
- [Mapika/decider-2b · Hugging Face](https://huggingface.co/Mapika/decider-2b)
- [Mapika/decider-2b-vision · Hugging Face](https://huggingface.co/Mapika/decider-2b-vision)
- [litert-community/decider-2b-vision-LiteRT · Hugging Face](https://huggingface.co/litert-community/decider-2b-vision-LiteRT)
- [GitHub - Mapika/decider](https://github.com/Mapika/decider)
- [Introducing Decision 1.0: Open Decision Foundation Models | vLLM Semantic Router](https://vllm-sr.ai/blog/decision-models/)
- [Decision 1.0 Towards Open Decision Foundation Models(论文 PDF)](https://vllm-sr.ai/decision-paper.pdf)
- [GitHub - vllm-project/semantic-router](https://github.com/vllm-project/semantic-router)
- [GitHub - wfzyx/von](https://github.com/wfzyx/von)
- [GitHub - IAMIbrahimmemon/von-mlx](https://github.com/IAMIbrahimmemon/von-mlx)
- [Is Jev open source? - devwithjev](https://devwithjev.com/guides/is-jev-open-source)
- [TypeSafe AI Releases Jev - MarkTechPost](https://www.marktechpost.com/2026/09/19/typesafe-ai-releases-jev/)
- [Jev AI Pricing Explained - MindStudio](https://www.mindstudio.ai/blog/jev-pricing-cost-per-token)
- [GitHub - ollaya-dev/ollaya](https://github.com/ollaya-dev/ollaya)
- [Jev alternatives: open-source reproductions, local models and classifiers | System One Models](https://systemonemodels.org/examples/alternatives/)
