# 项目状态(2026-10-04)

> 范围:2026-10-03/04 两天的进展汇总。更早的状态见 [project-status-2026-10-02.md](project-status-2026-10-02.md)。
> 标记:✅ 已验证 / 🏷 官方或用户提供、未独立验证 / ⚠ 未验证或有已知问题。质量判断均为助手自评,非用户独立验收。

## 1. 现在的位置

目标仍是"在本地算力和远程 GPU 之间找到最低成本、最有效的平衡点",并要求每次基准都附最优性审计(AGENTS.md 第31条)。
这两天完成了:本机延迟的受控实测与更正、云 GPU(腾讯云东京 Tesla T4)短租实测、把远程 GPU 接到产品命令和摄像头 demo。

## 2. 关键数字(同一模型 MiniCPM-V 4.6;各行输入与机器状态不同,只有标明"同一批图"的行可比)

| 配置 | 640 档 | 448 档 | 来源 |
|---|---|---|---|
| 本机 Ollama CPU(生产默认) | 16.8 秒 | 7.7 秒 | [延迟分布 §3.1](latency-distribution-2026-10-03.md) |
| 本机 llama.cpp CPU | 13.59 秒 | 5.17 秒 | 同上 §3.4(受控 A/B) |
| 本机 llama.cpp + Iris Xe(SYCL) | 6.49 秒 | 3.00 秒 | 同上 §3.4 |
| 本机 Ollama + Vulkan 核显 | 7.31 秒 | 4.90 秒 | 同上 §3.5;⚠ 公开图上 3/24 非法输出 |
| **T4 + llama.cpp(含约 0.4 秒跨洋往返)** | **0.96 秒** | **0.72 秒** | [T4 实测 §2.1](cloud-t4-results-2026-10-04.md)(同一批 12 张 COCO 图) |
| T4 + Ollama | 1.23 秒 | 0.98 秒 | 同上 |
| T4 + llama.cpp,经本机翻译层(连接池) | 约 0.68 秒 | — | 同上 §7(24 对交替) |
| 本机摄像头 demo → 翻译层 → T4 | 约 1.3 秒 | — | 用户口头转述,非受控 |

- **瓶颈:** 在 T4 上计算只占约 0.4–0.8 秒,往返时延(含每次新建连接的开销)约 0.4 秒,图片上传大小测不出差异。
- **成本(用户提供价 1.54 元/小时,1 元 ≈ 0.2125 加元):** 24 小时常驻约 236 加元/月,超出 100 加元预算;每天超过约 1.1 万次事件才比
  Gemini Flash-Lite 的按次计费便宜(API 价格来自 `scripts/cost_model.py`,API 的真实延迟没测)。标准按量价约为用户价的 5 倍(第三方站点,未核实)。
- **可靠性:** Ollama 对特定"图片 × 尺寸"组合会输出"坐标乱码"(非法 JSON),是**确定性**的、与并发无关:本机 Vulkan 顺序 3/24,T4 CUDA 顺序 3/46、8 路并发共 5/138;llama.cpp 在同样输入和其余全部请求里 0 个。根因未查清(假设:两边对同一张图的预处理/切块不同,未比较)。

## 3. 本阶段的更正(保留历史,已在原文档标注)

- 早先"核显路径没有明显优于 CPU"的 CPU 基线是缩图/缓存命中的数字 → 受控对照显示核显快 1.7–2.1 倍。
- "乱码是 Ollama Vulkan 路径特有"不成立(CUDA 并发下也出现)。
- llama-server 第一轮云端数据实际跑在 CPU 上(缺 CUDA 运行库,脚本缺陷),已修并标注;并发测试的缓存/冷加载污染已修并重跑。
- 第一版并排报告把 320×180 视频的"640 档/448 档"当成两个输入,实际是同一份像素,已改为自动合并并显示真实分辨率。

## 4. 代码与脚本变更(139 项测试通过)

- `src/visualintel/engine.py`:新增 `default_base_url()`,环境变量 `VISUALINTEL_OLLAMA_URL` 可指定模型地址;**默认不变**,
  默认只接受回环地址(`VISUALINTEL_ALLOW_NONLOOPBACK=1` 才允许别的主机)。
- `scripts/cloud/`:`run_cloud_suite.py`(客户端套件)、`setup_server.sh` / `restart_llama.sh` / `stop_servers.sh`(服务器端)、
  `ollama_facade.py`(Ollama 协议翻译层 + 上游连接池)、`connect_remote.ps1` / `start_local_llama.ps1`(启停,只结束自己启动的进程)、
  `compare_local_remote.py`(并排对比,远程模式只接受校验过的公开/合成视频)。
- 其他:`scripts/benchmark_scene_latency.py`、`prepare_cloud_testkit.py`、`cost_model.py` 等,见各文档。

## 4b. 手机应用(2026-10-04 晚新增,用户要求自主推进)

- 位置:`mobile/`(Expo SDK 57 / React Native 0.86 / TypeScript / expo-router)。设计与依据:
  [specs/2026-10-04-mobile-app-design.md](superpowers/specs/2026-10-04-mobile-app-design.md);使用与 TestFlight 步骤:[mobile/README.md](../mobile/README.md)。
- 已定决策(用户):建议性话术、按住说话、中英双语、AI 在本机/远程可切换(默认本机)、iOS 先 TestFlight。
- ✅ 验证过:Jest 204 项、`tsc` 0 错误、`expo lint` 干净、`expo-doctor` 21/21、Metro 能打出 Android 和 iOS 的 JS 包;
  **对真实 llama.cpp 模型跑了应用自己的提供方代码**(12 张公开图 × 中英)。
- 🔧 **实测后修订的设计:** 中文必须用**中文提示词**(英文提示词要求中文 → 0% 汉字,中文提示词 → 89%);模型会写"无危险/环境安全"(11 条中 8 条),
  所以加了安全断言拦截;场景标签约一半错误、置信度恒为 low → 删除 `scene`/`hazard_confidence` 和"友好场景提示";`hazard` 12/12 都是 `none`,
  无法证明有效 → 危险提示标为实验性,且**取消所有宽慰话**。详见设计文档。
- ✅ Android 模拟器(重启后内存够用):主界面、变焦按钮、设置页(同意对话框、填地址、测试连接"连接正常")、
  拍照→模型→结果的整条界面链路都走通,语音在缺原生模块时优雅降级;详见 mobile/README.md。
  ⚠ 模拟器拍照输出几乎全黑,所以没有展示带真实内容的界面结果;朗读出声、语音识别、真实变焦、本机推理、iOS 均未验证。
- ✅ 本地原生构建(无 Expo 云):`expo run:android` 约 11 分钟出调试包并装进模拟器;应用内下载 1.26 GB 模型并按字节校验通过。
- ⚠ **本机推理在 x86 模拟器上不可用**:载入约 52 秒,一张图的预处理超过 10 分钟仍未结束(2 vCPU、无 GPU;原因没查清),进程未崩溃。
  用户那次"崩溃"是一次返回手势把应用退到桌面。真手机速度未测。详见 [mobile/README.md](../mobile/README.md) "本机推理在模拟器上的实测"。
- 🔧 据此新增并单测:本机推理 120 秒超时(`too_slow`,建议改用远程)、等待秒数与首次载入提示、等待期间按钮变"取消"。
  另修一个实测发现的缺陷:设置页地址/密钥/模型名只在失焦时保存,直接点"返回"会丢失;改为边输入边保存(无单元测试,仅手动验证)。
- 模拟器可用电脑摄像头(`-camera-back webcam0`):预览显示了真实画面;模拟器控制台出现
  `convert_frame_fast: Failed to convert the camera frame`(BGR4→I420 转换失败、回退 RGB32),拍照路径是否受影响**待用户测试确认**。
- Expo:这台机器的 EAS 已登录为 `davyhan4`(邮箱 `tangmat@gmail.com`,组织 `davyhan4`、`wuva`),不是 `davyhanxc@gmail.com`;
  构建额度我没有查到(`eas account:view` 不显示用量),未用该登录创建项目或排队构建,等用户确认账号。
- ⚠ **没有验证:** iOS 任何运行时行为(本机是 Windows);语音识别、相机硬件变焦、朗读在真机上的表现;
  **本机模型(llama.rn + MiniCPM-V 4.6)在手机上的速度和内存**;真实远程服务器的 HTTPS 部署;TestFlight 构建本身。
- 需要用户做:Expo/Apple 账号登录、Bundle ID 确认(占位 `com.davyhan.visualhelper`)、`eas build` / `eas submit`。
  `WUVA_APP\BACKUP` 里的 Apple `.p8` 私钥我没有读取或使用。
- 不做:盲道/行走引导(P4),原因见设计文档 §6。

## 5. 未验证 / 未决

- ⚠ 修复后的安装脚本没有在一台**全新**机器上从零跑过;只在已装好的盘上验证过重跑(18 秒)。
- ⚠ 摄像头 demo 经远程只有用户口头反馈(约 1.3 秒);比受控测试高约 0.3–0.6 秒,原因未查。多帧 `report` 已在远程跑通(3 个片段、7.5 秒,需 `--parallel 1 -c 8192`;内容质量未逐段核对);`ask` 没测。
- ⚠ 质量只做了很小的自评抽查(4 张 COCO 图 × 5 个模型),不能排名;MiniCPM-V 4.6 在合成圆计数上不如其余四个模型(n=6)。
- ⚠ 托管 API 真实延迟、更近区域的往返时延、更强的 GPU(4090/L4)、手机端侧、OpenVINO(需下载约 2.6 GB,需用户批准)均未测。
- 决策待定:是否把 llama.cpp 作为默认引擎;是否做"本机门控 + 云端关键帧"的分层设计;是否做自定义镜像。

## 6. 用户待办

1. ~~终止测试实例~~:用户于 2026-10-04 告知实例正在销毁(用户口述;从本机已连不上该主机)。仍请在控制台确认每小时费用为 0,并检查快照、云盘、镜像是否还在计费。
2. 决定是否做自定义镜像;做之前先清理实例上的 shell 历史(里面有误敲进去的明文密码),见 [T4 实测 §8](cloud-t4-results-2026-10-04.md)。
3. 若要继续:托管 API 实测需要注册/密钥(由用户完成);手机端侧需要 iPhone / VIVO 的型号和系统版本。

## 7. 怎么恢复 / 复现

```powershell
cd E:\PROJECTX\VisualIntelligence
.\.venv\Scripts\python.exe -m pytest -q                                   # 139 项
.\.venv\Scripts\python.exe scripts\prepare_cloud_testkit.py               # 重建公开/合成测试集(已存在则校验)
.\scripts\cloud\connect_remote.ps1 -HostName <host> -KeyPath <专用私钥>    # 连接远程 GPU(-Stop 停止)
.\scripts\cloud\start_local_llama.ps1 -WithFacade                          # 本机核显服务(-Stop 停止)
```

云实例的安装与测试流程见 [云 GPU 测试手册](cloud-gpu-test-runbook-2026-10-03.md)。
