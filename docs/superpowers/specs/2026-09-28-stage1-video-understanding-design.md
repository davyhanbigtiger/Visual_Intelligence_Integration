# Stage 1 设计文档:离线视频理解引擎(VLM-only)

> 2026-10-02 范围补充：原离线设计与验收记录保留；用户后续授权增加 `scene`
> 和独立 Windows 11 `camera` demo。历史“不做摄像头”仅指原 Stage 1 范围。
> 默认仍为 MiniCPM；SmolVLM-500M CPU 是未来 Plan B/辅助候选，未接入自动切换。
> 摄像头读取、预览 smoke test、一次模型调用已验证，连续质量待验收；
> 最新 87 项测试通过，见 [项目状态](../../project-status-2026-10-02.md)。

> 状态:brainstorming 已完成方案对比与分段设计确认,本文档是正式 spec,
> 已批准并实现 Stage 1 代码，真实场景质量验收仍待完成。背景/目标/约束的完整推导过程见
> [../../project-goals.md](../../project-goals.md)、
> [../../hardware-inventory.md](../../hardware-inventory.md)、
> [../../open-source-landscape.md](../../open-source-landscape.md)。本文档只记录
> **这一版要实现什么、怎么实现**,不重复背景论证。

## 1. 范围

- 处理**用户手动放入 `videos/` 目录的视频文件**(离线,不涉及摄像头采集、
  实时流媒体、设备联调)
- 不要求亚秒级延迟,允许单个视频处理耗时数十秒到数分钟
- 用一个统一的理解引擎支持两种查询方式:自动生成报告 / 针对视频提问(VQA)
- 明确不做:独立的目标检测/追踪模型、向量索引/RAG 基础设施(见第2节方案
  对比的取舍理由)——这些在 Stage 1 验证受阻时再升级,不是现在的任务

## 2. 已确认的架构方案:方案 A(VLM-only 单体管线)

对比过三个方案(VLM-only / VLM+独立检测器 / VLM+RAG索引),选定 **VLM-only**:
用一个视觉语言模型同时承担场景理解、异常提示、情境判断/行动建议,不引入
独立检测器(避免过早引入 YOLO26 的 AGPL-3.0 许可证问题),不预建检索索引
(Stage 1 视频数量少、时长短,收益低于工程成本)。

**起点模型**:MiniCPM-V 4.6(OpenBMB,Apache-2.0),通过 Ollama 本地部署。
已完成 spike 验证(见 open-source-landscape.md):单图约32.6秒、6帧视频约
68.7秒(纯CPU),能正确追踪帧间的时序变化,`think:false` 可消除思考过程
泄漏。**不是最终锁定的模型**——如果后续发现理解质量不够(尤其是生僻场景),
升级路径是接入云端 Qwen3-VL 等更强模型,接口设计上应保持"可替换底座模型"。

## 3. 目录结构与组件

```
VisualIntelligence/
  videos/                    # 用户放测试视频(gitignore)
  outputs/                   # 生成的报告(gitignore)
  src/visualintel/
    sampling.py               # 纯函数:采样时间点计算、chunk分组
    engine.py                  # 封装 Ollama 调用:prompt拼装、think:false、UTF-8
    report.py                  # 汇总chunk结果为 JSON/Markdown 报告
    cli.py                      # 命令行入口
  tests/
    test_sampling.py
    test_report.py
```

两个命令行入口,共享同一套采样与模型调用代码:

```bash
python -m visualintel report videos/x.mp4
python -m visualintel ask videos/x.mp4 "有没有人在打电话?"
```

依赖:opencv-python(已安装,用于抽帧)+ Python 标准库(`urllib`、`json`、
`pathlib`),不引入额外的网络请求库或框架。

## 4. 数据流与参数

- 默认每 **2秒采1帧**,每次 VLM 调用最多带 **8帧**(约覆盖16秒),超过则
  分成多个 chunk;**默认最多处理20个chunk**(约5.3分钟视频,可配置),
  超过则截断并在报告中注明"仅处理前N分钟"
- 每个 chunk 产出一条结构化记录,汇总为整段视频的报告
- **多个 chunk 之间以最多4路并发处理,不是顺序排队**(2026-09-29 硬件
  探索的实测结论,见 [../../benchmark-matrix.md](../../benchmark-matrix.md)
  "并发实验结论":在这台机器上4路并发比顺序处理快5.05倍,8路反而更慢,
  说明4是这块硬件的并行度上限,不是随便选的数字;换后端/硬件时这个并发
  数可能需要重新测,不保证是普适最优值)。结果必须按 chunk 时间顺序回填,
  不能因为并发完成顺序不同而打乱

## 5. 输出 Schema

```json
{
  "video": "videos/x.mp4",
  "duration_sec": 32.0,
  "truncated": false,
  "chunks": [
    {
      "start_time": 0.0,
      "end_time": 16.0,
      "status": "ok",
      "description": "画面里发生了什么(客观描述)",
      "unusual_flag": { "flagged": false, "note": "" },
      "guidance": {
        "assessment": "建议性语气的整体判断",
        "suggestion": "建议性语气的具体提示,尽量给出方位/距离等具体信息",
        "confidence": "low | medium | high",
        "disclaimer": "该判断基于有限画面自动生成,仅供参考,不能替代现场判断、专业培训或辅助工具/人员的帮助。"
      }
    }
  ]
}
```

- `disclaimer` 文本由代码固定拼接,**不依赖模型输出**,保证每条 guidance
  都一定带有免责说明
- `status` 为 `"failed"` 的 chunk 只保留错误信息,不编造 description

## 6. 输出语气规则(安全相关的硬性要求,非可选)

背景与理由见 project-goals.md §3/§4(无障碍出行/导航辅助已确认是必须覆盖
的场景之一,但系统不能被当作安全关键指令来源)。具体要求:

1. **情境判断/建议部分禁止使用祈使句式的确定指令**(如"往左走""必须用
   绳索"),必须用观察+建议的语气(如"看起来……,可能需要考虑……")
2. **建议要具体,不能只给空泛的安全评级**——优先给出方位、距离、障碍物
   类型等具体信息,"具体"和"带不确定性的语气"不矛盾,两者都要做到
3. **事实性问题不附加 guidance**;只有当问题本身是在求建议时,才触发
   guidance 部分的语气规则(通过 `ask` 命令的 prompt 分支处理)
4. Prompt 模板草案:

```
Describe what happens in these frames (sampled in order from a video clip).
Then separately assess: does this situation seem safe or does it need
caution? Do NOT give commands or absolute instructions (avoid "go left",
"you must use X"). Instead phrase it as an observation and a soft
suggestion with specific details when possible (e.g. "there appears to be
a step down about 2 meters ahead on your right"), always acknowledging you
are working from limited visual information, not ground truth. Finally,
state your own confidence in this assessment as exactly one of: low,
medium, high — based on how clear and unambiguous the frames are.
```

`confidence` 字段由模型在 prompt 末尾按要求自报(low/medium/high),不是
代码计算出来的——这是模型自我评估,本身也可能不准,报告里呈现时需要说明
这一点,不能当作精确的置信度分数使用。

## 7. 错误处理

- 视频文件读取/解码失败 → 记录错误、跳过该文件,不中断批处理
- 处理前先检查 Ollama 服务是否运行、模型是否已 pull,不满足直接报错退出
- 单个 chunk 调用失败 → 重试1次,仍失败标记 `status: "failed"`,不影响
  其他 chunk
- 视频过长 → 按第4节的 chunk 数上限截断,报告中如实注明
- 所有文件读写显式使用 UTF-8 编码(对应 spike 中发现的控制台乱码问题)

## 8. 测试计划

- **自动化单元测试**(确定性逻辑,不需要跑模型):
  - `sampling.py`:给定 fps/时长/采样间隔,验证采样点和 chunk 分组正确
  - `report.py`:给定构造好的 chunk 结果,验证 JSON/Markdown 输出格式正确
- **人工抽查**(端到端效果,LLM输出有随机性,不能写成自动断言,如实按
  AGENTS.md 第13条标注为"人工抽查通过"而非"自动化测试通过"):
  - 用已录制的测试视频跑 `report` 命令,检查输出合理性
  - **新录一段带真实障碍物/需要绕行的素材**,专门检查 guidance 部分是否
    给出具体、有用的建议(而不是空泛的"注意安全")
  - 用 `ask` 分别测试一个事实性问题和一个"我该怎么走"类问题,确认语气
    规则只在后者生效
- **异常路径测试**:故意提供损坏视频文件、故意不启动 Ollama 服务,确认
  报错清晰,不会卡死或抛出未处理的 stack trace

## 9. 明确不做(YAGNI,本版范围之外)

- 不做实时摄像头采集/推流(见 project-goals.md §5,未来阶段的事)
- 不做独立目标检测/追踪模型(避免过早引入 AGPL-3.0 依赖)
- 不做向量索引/RAG(视频数量少时收益低于成本)
- 不做多用户、鉴权、云端部署等产品化基础设施

## 10. Stage 1 manual verification log（2026-09-30）

### 已验证

- 环境：本机 Windows、Python 3.12.8；独立 `.venv` 中安装
  opencv-python 5.0.0.93、pytest 9.1.1；`pip check` 无依赖冲突。
- 自动化（初轮实现）：63 项 pytest 测试通过，包括真实合成视频的抽帧、并发顺序、
  模型失败重试、错误退出码、已有报告保护、UTF-8 控制台输出。
  模型响应使用 mock，测试通过不代表理解质量通过。
- `ollama list` 确认本机 `minicpm-v4.6:latest` 已安装。
- 复用此前 spike 的 `test_video.avi`，原素材保留，副本置于 `videos/`。
  OpenCV 读取到 179 帧、15 fps，时长约 11.93 秒；报告采样
  0/2/4/6/8/10 秒六帧。真实 `report --workers 1` 返回 0，生成
  `outputs/smoke-20260930/report.json` 与 `report.md`，中文固定免责声明存在。
- 本轮助手对抽样帧的视觉核对（尚未经用户独立人工复核）：人物先触碰头颈/嘴部，随后拿白色杯子，模型的
  主体动作描述基本与可见画面一致。这是单片段核对，不代表跨场景能力。
- 缺失视频命令返回 1，错误清晰；不可连接的本地端口验证产生
  `EngineNotReadyError`。未停掉现有 Ollama 服务来测试。
- 已有报告再次运行被拒绝，原文件保留。

### 发现与修复

- 首次真实报告的建议包含 “Do not …” 指令语气，且异常标记为 true
  但说明为空。原报告保留以供复查，未手改成“合格”输出。
  已增加部分明显英文/中文指令句的拦截，替换为不提供行动建议的说明，
  confidence 降为 low。该规则已通过回归测试，但不是完整语义安全校验。
- 首次真实事实问答在 Windows 控制台出现 `charmap` 编码失败，退出 1；
  已修复 CLI stdout/stderr 为 UTF-8，并添加真实编码流的回归测试。
- 真实建议问题 “Does this scene need caution, and what might I consider?”
  用时约 117.73 秒，命令返回 0，但模型将 `GUIDANCE` 写成 `GUIDENCE`，
  原解析漏加免责声明，且使用 “Consider …” 指令语气，内容缺少具体细节。
  已兼容该拼写并扩大明显指令拦截规则。原输出保留在
  `outputs/verification/advice-ask.txt`，最终代码对该真实输出的回放结果
  保存在 `advice-ask-guarded.txt`：建议被暂扣并添加固定免责声明。
  这是对真实输出的解析回放验证，不是声称修复后又跑了一次同样的模型调用。
- UTF-8 修复后真实事实问答重新运行成功，返回 0，用时约 209.47 秒；
  描述人物、眼镜、白杯与手部动作基本符合抽样画面，但模型仍附加了
  GUIDANCE。原输出保存在 `outputs/verification/factual-ask.txt`。
  已增加问题关键词分类：事实问题丢弃 guidance，求建议问题即使模型没有
  给出字段标记也拼接免责声明，并对明显指令句进行拦截。
  原输出的过滤回放保存在 `factual-ask-filtered.txt`，分类行为通过中英文
  回归测试。该分类是启发式规则，复杂问题仍可能误判；本轮未再重复整个
  昂贵的模型调用来验证最后的确定性解析修改。

### 尚待验收

- 新录制的真实障碍物/绕行视频未提供，未主动启动摄像头采集。
- 导航建议的具体性未通过本轮抽查；事实问题与建议问题的稳定区分、模型
  完全忽略字段格式时的处理，仍需进一步验证。当前规则不能保证识别所有
  指令措辞或建议语义。
- 4 路并发在本项目 Ollama 后端的实际收益未测；既有 5.05 倍数据属于
  llama.cpp/SYCL 单帧实验，不作为本实现性能承诺。
- 当前结论：Stage 1 工程框架可运行；建议质量仍需迭代，不能认定整个
  Stage 1 已完成质量验收，也不能据此进入机器人控制阶段。

HTTP 接口实现对照了 [Ollama generate](https://docs.ollama.com/api/generate)
与 [模型列表](https://docs.ollama.com/api/tags) 官方文档；本轮没有重新审核
历史调研文档中的全部模型、许可证和性能结论。

### 后续迭代（2026-09-30）

继续进行了真实模型与结构化输出对照，新增 JSON Schema、输出上限、
校验失败后的定向修复重试，以及显式问答类型选择。
当前 83 项自动化测试通过；真实生产流程的报告/事实问答/建议问答均实际运行。
质量缺陷与候选模型结论见 [本轮评估](../../model-evaluation-2026-09-30.md)。
以上运行成功不等于导航建议质量通过，仍未完成 Stage 1 独立人工验收。
