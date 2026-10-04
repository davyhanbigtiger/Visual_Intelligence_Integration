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
