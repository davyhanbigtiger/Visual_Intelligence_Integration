# 环境概况延迟：候选模型与优化路径（2026-09-30）

> 后续已完成SmolVLM500M与OpenVINO CPU/GPU实验，见
> [追加评估](smolvlm-openvino-evaluation-2026-09-30.md)。以下“尚未测/下一候选”
> 保留为本轮调研时的状态，最新判断以追加评估为准。

当前优化目标是场景类别、主要人物与显眼物体。速度与描述正确性同时考核，
不以复杂推理、导航建议或隐藏物体细节作为筛选目标。

## 本轮可直接确认的结果

同一台 i7-1355U / Iris Xe 笔记本、同三张 Google 搜索找到的公开图。
图片来源与助手视觉参照见 environment-awareness-evaluation-2026-09-30.md。

| 路径 | 餐饮区 | 烹饪摊 | 公园入口 | 判断 |
|---|---:|---:|---:|---|
| MiniCPM / Ollama，最长边640 | 16.81s | 17.80s | 17.81s | 环境概况吻合 |
| MiniCPM / Ollama，最长边320 | 14.55s | 6.34s | 6.74s | 主要环境吻合；烹饪设备等细节丢失 |
| SmolVLM-256M Q8 / llama.cpp CPU，640，简单文本caption | 2.11s | 2.16s | 2.20s | 烹饪摊和公园较好，餐饮区错误描述为小村庄并猜招牌文字 |
| SmolVLM-256M Q8 / llama.cpp CPU，320，简单文本caption | 2.26s | 2.40s | 2.38s | 餐饮区较好，烹饪摊猜“卖菠萝”，公园入口误读为Rail |

每组每图仅一次；顺序测试，没有随机化或稳态重复。这里同时改变了模型、
后端与提示词，不能把速度差归因于单一因素，不能宣称稳定加速倍数。
SmolVLM 文本提示为 `Describe this image in one short sentence.`，temperature=0、
seed=42、max_tokens=64；MiniCPM 使用生产scene prompt、JSON字段、96 tokens上限。
六次简单文本均正常结束。llama.cpp 返回缓存输入token数为0，配置关闭prompt缓存，
但不同缩放组可能仍受视觉/进程缓存及系统负载影响。

MiniCPM 320结果原文：

- 餐饮区：A sunny outdoor area with people walking, visible buildings, and trees, suggesting a public space for leisure.
- 烹饪摊：Outdoor market setting with people handling items, visible cups, and a red car nearby.
- 公园：The image shows a park entrance with people near the entrance, surrounded by greenery and buildings in the background.

概况可接受不代表每个细节已验证：“leisure”是环境解释，静态图中的walking是
姿态推断，cups不是该烹饪摊中最突出且最确定的物体。仅助手看图核对，非独立人工验收。

### SmolVLM 结构化失败与部署隔离

先尝试相同scene prompt与JSON Schema：首张耗时3.03s，但输出重复、不完整
JSON及乱码，达到96 token上限。记录为失败，不混入有效耗时。
随后打印乱码时实验脚本触发Windows cp1252编码错误；原始JSON记录已保存，
通过UTF-8 stdout修复实验脚本后继续简单文本测试。这不是模型有效成功。

使用已有官方llama.cpp b11146（7fe450e19）SYCL发行包，但显式
`--device none -ngl 0 --no-mmproj-offload`，实际测试CPU路径。
服务只绑定127.0.0.1:18937，ctx2048、parallel1、no-cache-prompt、reasoning off。
测试结束停止本次创建的子进程；原Ollama服务不变。没有安装新Python依赖。
模型下载在独立outputs目录，原模型、文件均保留；生产默认仍为MiniCPM。

GGUF来自[ggml-org官方转换仓库](https://huggingface.co/ggml-org/SmolVLM-256M-Instruct-GGUF)，
固定revision `b9e4379657e1450d04d02eec8e345667265b0a00`，主模型175,054,528字节，
视觉文件103,769,856字节。该转换仓库最近修改时间为2025-04-30；没有据此
假定它跟随最新上游权重。源码引擎与权重的维护是不同维度。

原始配置、响应和日志：`outputs/latency-research-20260930/smolvlm-256m/`。
MiniCPM新增320对照：`outputs/google-scene-evaluation-20260930/resized-320/`。

## 候选与适用性

| 候选 | 已核实事实 | 对当前项目的判断 |
|---|---|---|
| [SmolVLM-256M](https://huggingface.co/HuggingFaceTB/SmolVLM-256M-Instruct) | Apache-2.0；较小93M视觉编码器，512像素图块/64视觉tokens，英文模型 | **有希望但仍实验**：本机2秒级可行，但本轮错误较多，不能直接默认替换 |
| [SmolVLM-500M](https://huggingface.co/HuggingFaceTB/SmolVLM-500M-Instruct) | Apache-2.0；官方提供模型与公开评测；同样描述较小视觉编码器架构 | **下一候选**：更可能平衡质量与速度；本机尚未测，不承诺秒数 |
| [OpenVINO + Optimum Intel](https://huggingface.co/blog/openvino-vlm) | 官方示例支持SmolVLM2-256M转换、CPU/Intel GPU与量化视觉编码器 | **下一优化路径**：专门针对Intel，值得独立环境实测；尚未安装部署 |
| [Florence-2-base](https://huggingface.co/microsoft/Florence-2-base) | MIT，0.23B，支持CAPTION/DETAILED_CAPTION等固定任务 | **有希望的caption备选**：贴合简短环境描述，不是现有自由问答接口的直接替代；需单独后端与版本适配 |
| [Apple FastVLM](https://github.com/apple-aiml-research/ml-fastvlm) | 专门优化视觉编码器，提供iOS/Apple Silicon部署示例 | **当前Windows不优先**；研究模型许可排除产品开发/商业用途，适合研究评估而非直接产品部署 |

FastVLM的[模型许可](https://github.com/apple-aiml-research/ml-fastvlm/blob/main/LICENSE_MODEL)
与代码许可分开；不能因源码公开而把权重当作Apache/MIT使用。
其“85倍TTFT”是在指定LLaVA-OneVision比较条件下的作者结果，不是对MiniCPM
或本机的保证。本轮未部署FastVLM、Florence或OpenVINO。

Intel/Hugging Face[官方OpenVINO示例](https://huggingface.co/blog/openvino-vlm)
报告SmolVLM2-256M单图WOQ端到端0.482秒，测试机为Core Ultra 7 265K、
20核、64GB DDR5、Ubuntu，**不是我们的低功耗i7-1355U**。
此数据只是优化路线证据，不能当本机预测。OpenVINO的
[系统要求](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino/system-requirements.html)
包含Iris Xe；设备被支持不代表所有VLM组件在该设备都更快。
已核实的SmolVLM2示例是Optimum的OVModelForVisualCausalLM路径，不能直接
假定OpenVINO GenAI VLMPipeline对所有SmolVLM版本具有同样支持。

## 基础维护与风险检查

本轮通过GitHub官方API查看仓库状态、最新commit与release，摘要保存于
`outputs/latency-research-20260930/github-health.json`：

- llama.cpp：MIT，未归档，最新commit日期2026-09-30；release v0.5.0日期2026-09-23。
- huggingface/smollm：Apache-2.0，未归档，最新commit日期2026-09-23，无latest release对象。
- OpenVINO GenAI：Apache-2.0，未归档，最新commit日期2026-09-30；release2026.4.0.0日期2026-09-17。
- Apple FastVLM：已转到apple-aiml-research，未归档，最新commit日期2026-09-11，无latest release对象。

这只是基础健康检查，不是依赖漏洞审计、全部关键issue审核或维护者集中度审计。
[llama.cpp issue27190](https://github.com/ggml-org/llama.cpp/issues/27190)报告旧SmolVLM-Instruct
token问题，报告者注明256M/500M等不受该问题影响；不代表这些变体不存在别的问题。
Florence原模型卡代码使用trust_remote_code=True；后续实验应优先核对
[Transformers原生Florence2支持](https://github.com/huggingface/transformers/blob/main/docs/source/en/model_doc/florence2.md)，
固定依赖/权重版本并使用独立环境，不直接复制安装说明修改当前venv。

## 建议顺序

1. 保留MiniCPM为质量基线，以320/640做场景概况的速度与细节取舍；需更多未测图片。
2. 同组图实测SmolVLM-500M，判断是否能保留256M的低延迟且减少场景误判。
3. 在独立环境验证SmolVLM2-256M/500M + OpenVINO CPU，再对照Intel GPU；
   CPU不应被跳过，过去核显路径并未保证更快。
4. 如果只需固定一句caption，Florence-2可作为另一条路线；暂不添加YOLO/RAG等额外层。

视频未来可增加画面变化触发：无明显变化时复用最近概况，必须显示原观察时间与
结果年龄。这减少调用数量，不会降低一次新画面的推理延迟，也可能漏掉小物体变化，
本轮未实现。并发提高批量吞吐，不等同于单次低延迟。

缩短输出、流式返回、常驻模型可以分别减少生成量、等待感或冷加载，但本次输入
处理占主要时间，不能据此期待数量级提升。新图与重复图的缓存表现须分开测试。
