# SmolVLM-500M 与 OpenVINO 后续实测（2026-09-30）

继 latency-options-2026-09-30.md 继续执行用户授权的实验。生产默认仍为
MiniCPM/Ollama；本轮实验使用独立 outputs 目录和独立 Python 环境。

用户确认的模型决策（2026-09-30）：保留 MiniCPM-V 4.6 / Ollama 为默认模型；
SmolVLM-500M / llama.cpp CPU 保留为未来 Plan B 或辅助模型候选。当前不启用
自动降级或双模型调用；接入前须验证目标场景的描述质量及失败处理。

## SmolVLM-500M / llama.cpp CPU

使用已有官方 b11146 / 7fe450e19 llama-server，显式禁用语言模型与视觉部分
GPU offload，端口127.0.0.1:18937，ctx2048、parallel1、关闭prompt缓存。
模型来自 [ggml-org](https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF)，
通过HF API固定revision，来源、SHA256与启动参数保存于
`outputs/latency-research-20260930/smolvlm-500m/`。

沿用三张公开图，再加入此前核对的COCO室内图与真实视频第120帧
（人物红衣、眼镜、持白色杯子）。参照是助手视觉检查，不是独立人工验收。
五图顺序、每尺寸各一次，没有随机顺序或稳态重复；冷加载不计入请求耗时。

| 图像 | 640耗时 | 640输出要点 | 320耗时 | 320输出要点 |
|---|---:|---|---:|---|
| 户外店铺 | 2.60s | 人在店铺前，像公园区域；合理 | 2.77s | 人、店铺、宽阔步道；合理 |
| 烹饪摊 | 2.91s | 红遮棚下的食物摊；合理 | 3.04s | 市场/红遮棚，猜招牌Mini Pine；部分正确 |
| 公园入口 | 2.91s | 公园入口与灰色石材；合理但概况有限 | 3.52s | 误称Cherry Street Plaza、大建筑；环境概况不合格 |
| COCO室内 | 2.99s | 女人在厨房烹饪；动作未确认，漏掉主要家具 | 3.89s | 客厅、餐区、挂钟；较符合目标 |
| 人物持杯 | 2.89s | 猜自拍、咖啡、粉色杯柄；不合格 | 4.04s | 白杯但猜勺子、壁炉；不合格 |

文本prompt：`Describe this image in one short sentence.`；temperature0、seed42，
输出上限64tokens，十次正常结束。这里只测试简短caption；不代表模型能够
回答任意问题、理解时间线或生成建议。

### 结构化对照与实验方法修正

采用现有SCENE_PROMPT/FACTUAL_SCHEMA、96tokens，640像素五图。
启用`--jinja`并使用`response_format={type:json_object,schema:...}`后，五次
均满足字段与长度检查，耗时3.04/4.21/4.35/4.35/4.95秒。
但answer依次为：人在店铺前、Mini Lime Pine、cherry street park、
照抄“do not guess hidden contents, identities or intentions”、happy birthday。
后三类不充分或不相关回答说明复杂指令并不适合直接当作该小模型的caption提示。

此前无Jinja的试验包含错误字段/截断，全部原始结果保留于structured-corrected/。
需更正上一轮判断：master文档示例与固定b11146源码参数形式有差异；
[固定源码](https://github.com/ggml-org/llama.cpp/blob/7fe450e19/tools/server/server-common.cpp)
支持原先的嵌套json_schema/schema参数。不能把之前失败简单归因于参数形式
错误，也不能把这次改善仅归因于更换参数；本次同时启用Jinja。

256M也补测相同Jinja/schema设置：两张字段有效，首张仍乱码/截断。
所以既有失败是真实记录，但不是“256M所有配置均不支持JSON”的证据。

### 当前结论

500M短caption比256M在三张640公开图上更稳定，但扩展至室内/人物后仍有
明显无依据推断。低延迟是已观察结果，全面优于MiniCPM尚未成立。
暂不更换默认引擎。输入320也并非总能更快或更准确，不能自动认为越小越好。

## OpenVINO 环境与来源

独立venv位于 `outputs/latency-research-20260930/openvino-env/`，不改项目venv。
先安装官方CPU torch2.8.0，固定Optimum Intel1.25.2、Transformers4.53.3、
OpenVINO2025.2.0以接近[官方示例](https://huggingface.co/blog/openvino-vlm)。
这是复现实验版本，不是建议生产采用旧依赖；生产安全/升级审核尚未完成。

模型使用官方博客链接的HF工作人员预转换8bit WOQ
[SmolVLM2-256M](https://huggingface.co/echarlaix/SmolVLM2-256M-Video-Instruct-openvino-8bit-woq-data-free)，
固定revision，存于openvino-256m-model/；不执行remote model Python代码。
这是SmolVLM2，与前述SmolVLM500M不同，不能将速度差只归因于OpenVINO。

复现脚本：scripts/evaluate_llama_scenes.py、scripts/evaluate_openvino_scenes.py。
实验输出目录必须不存在，保存每图结果、来源与配置。llama脚本只停止自己
启动的测试子进程，不操作原Ollama服务。OpenVINO记录加载/编译与每次请求
（含PIL预处理）分别耗时，首次请求另标记。

## OpenVINO 结果与改进

实际依赖修复：初次Optimum导入失败，自动解析的NNCF3.4需要OpenVINO2025.2
不存在的Type.u2；固定NNCF2.18.0后解决。随后补齐CPU Torchvision0.23.0与
num2words（SmolVLM的video processor初始化也要求这两项，即使只处理静态图）。
这些安装/启动失败全部保留日志，不计为推理成功。最终`pip check`无冲突，
完整版本保存在openvino-freeze-final.txt，项目venv未改动。

默认处理器配置size.longest_edge=2048，虽然传入图片最长边只有640，处理器
仍重新放大并生成13个512×512图块，input_tokens=878。显式设为512后
实测只有1个512×512图块，input_tokens=83。修改只作用于实验进程的processor
对象，没有覆盖预转换模型、原图或原始配置文件。

| 图像 | CPU默认13块 | CPU限制1块 | GPU限制1块 |
|---|---:|---:|---:|
| 户外店铺 | 20.60s | 4.87s，达到64tokens上限 | 8.34s，60tokens |
| 烹饪摊 | 23.78s | 2.98s，27tokens | 3.33s，29tokens |
| 公园入口 | 22.49s | 4.19s，达到64tokens上限 | 5.82s，达到64tokens上限 |
| COCO室内 | 24.13s | 2.09s，18tokens | 3.80s，50tokens |
| 人物持杯 | 22.96s | 2.83s，35tokens | 1.55s，18tokens |

上表为模型已加载/编译后的请求时间，包含图片PIL预处理，不含Python启动
及import、模型加载/编译。CPU加载编译约3.91s（默认）/4.35s（限制），
GPU约48.42s。GPU组不复用CPU运行的模型实例，逐组运行避免互相争抢资源。
全部仍是每图每组一次，无法据此计算稳态p50/p95或保证长期运行速度。

默认CPU组五张640已完成，随后核对并停止本次评估器子进程PID15248，
不继续重复320组；completed-baseline.json与stopped.json明确保存此状态。
该批评估器退出1是主动停止，不宣称整批正常完成。后续限制CPU/GPU组均完整
运行五张并正常退出0；退出0只表示运行完成，不表示内容质量合格。

质量核对：

- 默认13块：店铺/市场/室内概况大致正确，但烹饪摊中“洗蔬菜”动作未确认；
  公园错误强调“建筑前的招牌”。人物持杯的主对象正确。仍有细节推断。
- CPU1块：室内正确概括客厅/餐区/电视/餐桌；人物持白杯正确，另猜站立和饮用；
  市场概况基本正确，但部分衣服颜色解释未确认。店铺与公园输出变长/重复，
  达到64tokens并明显未完句；公园还误称大楼，不能作为有效短caption。
- GPU1块：人物持杯正确，但保留“可能喝东西”推断；市场大致正确；公园描述
  达上限且把logo猜为樱桃；室内猜人物正在看电视、墙色与窗户等未确认细节。

CPU/GPU在相同贪心参数下答案长度与内容也不同，因此时间差包含生成量变化
和后端数值差异，不能说GPU恒定更快或结果完全一致。本轮CPU整体更省事，
GPU只在一个短输出样本显著更快，不推荐为此默认启用GPU。

仍可见旧版本非致命warning：预处理video配置布局弃用、ONNX符号重复注册、
Optimum尝试推断本地模型转换状态时构造了无效HF缓存路径。程序继续加载本地
IR并生成结果；warning完整保留日志，不能把它们隐去并声称部署无问题。

### 结论与可用范围

**已验证的改进线索**是显式控制视觉处理器的内部尺寸/图块数，并保持模型
常驻。仅缩小上传文件不保证减少实际视觉计算量。限制一块把此次OpenVINO
请求从20–24s降至2–5s，但同时出现质量退化和输出变长，不能只报告最快数字。

SmolVLM500M/llama.cpp CPU短caption约3s，依赖与启动较简单；OpenVINO512
在部分样本更快，但安装兼容成本与冷编译更高。目前两条均分类为
**有希望但实验性**，不替换MiniCPM/Ollama默认，不将任意结果视作安全/导航结论。

本轮只接入可复现实验脚本，没有往生产CLI引入OpenVINO依赖。后续如选择
试用快速模式，应作为常驻进程、简短caption能力，明确结果年龄与模型来源，
并先扩大未测图像集核对场景类别，不能把五张结果当完整验收。

验证：现有85项测试通过，脚本compileall通过；原Ollama仍可访问，测试
llama-server端口18937关闭，所有图像/模型/失败日志保留，无提交或推送。
