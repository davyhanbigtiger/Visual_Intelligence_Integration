import type { Language } from '../core/types';

export interface SettingsStrings {
  title: string;
  engine: string;
  local: string;
  remote: string;
  localHelp: string;
  remoteHelp: string;
  model: string;
  modelReady: string;
  modelMissing: string;
  modelPartial: string;
  download: string;
  downloading: (percent: number) => string;
  cancelDownload: string;
  downloadFailed: string;
  wifiHint: string;
  deviceFit: { ok: string; tight: string; too_small: string; unknown: string };
  serverAddress: string;
  serverAddressHint: string;
  apiKey: string;
  apiKeyHint: string;
  modelName: string;
  testConnection: string;
  testing: string;
  testOk: string;
  testAuth: string;
  testUnreachable: string;
  testTimeout: string;
  testUnexpected: string;
  urlProblems: { empty: string; invalid: string; scheme: string; https_required: string };
  language: string;
  speakResults: string;
  voice: string;
  voicePrivacy: { on_device: string; maybe_cloud: string; unavailable: string };
  safetyTitle: string;
  safetyBody: string;
}

export const SETTINGS_STRINGS: Record<Language, SettingsStrings> = {
  zh: {
    title: '设置',
    engine: 'AI 运行位置',
    local: '本机 AI',
    remote: '远程服务器',
    localHelp: '在手机上运行,画面不离开手机,可离线使用。需要先下载约 1.2 GB 的模型,速度取决于手机。',
    remoteHelp: '把画面发送到你自己设置的服务器,通常更快。画面会经过网络,只使用你信任的服务器。',
    model: '本机模型(MiniCPM-V 4.6)',
    modelReady: '已下载,可以使用',
    modelMissing: '还没有下载',
    modelPartial: '下载不完整,需要重新下载',
    download: '下载模型(约 1.2 GB)',
    downloading: (p) => `正在下载 ${p}%`,
    cancelDownload: '取消下载',
    downloadFailed: '下载失败,请检查网络后重试。',
    wifiHint: '建议连接 Wi-Fi 再下载。',
    deviceFit: {
      ok: '这台手机的内存看起来够用(估算,未实测)。',
      tight: '这台手机内存可能偏紧,运行时可能被系统关闭(估算,未实测)。',
      too_small: '这台手机内存可能太小,不建议使用本机 AI(估算,未实测)。',
      unknown: '无法判断这台手机的内存是否够用。',
    },
    serverAddress: '服务器地址',
    serverAddressHint: '例如 https://你的服务器。公网必须用 https;局域网可用 http。',
    apiKey: '访问密钥(可选)',
    apiKeyHint: '保存在系统钥匙串中,不会写入普通设置。',
    modelName: '模型名称',
    testConnection: '测试连接',
    testing: '正在测试…',
    testOk: '连接正常。',
    testAuth: '服务器拒绝了访问密钥。',
    testUnreachable: '连不上服务器,请检查地址和网络。',
    testTimeout: '服务器响应超时。',
    testUnexpected: '服务器返回了意外的结果。',
    urlProblems: {
      empty: '请填写服务器地址。',
      invalid: '地址格式不正确。',
      scheme: '只支持 http 或 https。',
      https_required: '公网地址必须使用 https,否则画面和密钥会明文传输。',
    },
    language: '语言(界面、回答、朗读、语音识别)',
    speakResults: '朗读结果',
    voice: '语音',
    voicePrivacy: {
      on_device: '语音识别在手机上完成。',
      maybe_cloud: '这个语言的语音识别可能使用系统的云服务。',
      unavailable: '此版本不支持语音识别,请用按钮。',
    },
    safetyTitle: '请注意',
    safetyBody:
      '这是一个由人工智能生成描述的辅助工具,不是安全设备,也不是导航工具。它可能看错、漏看,单帧画面不能说明周围是否安全。' +
      '它不能代替你自己的判断、白手杖、导盲犬或他人的帮助。请不要在过马路、行车、攀爬等危险场合依赖它。',
  },
  en: {
    title: 'Settings',
    engine: 'Where the AI runs',
    local: 'On-device AI',
    remote: 'Remote server',
    localHelp: 'Runs on your phone: pictures stay on the phone and it works offline. You need to download a model of about 1.2 GB first; speed depends on the phone.',
    remoteHelp: 'Sends pictures to a server you set up, usually faster. Pictures travel over the network, so only use a server you trust.',
    model: 'On-device model (MiniCPM-V 4.6)',
    modelReady: 'Downloaded and ready',
    modelMissing: 'Not downloaded yet',
    modelPartial: 'Incomplete download; it needs to be downloaded again',
    download: 'Download model (about 1.2 GB)',
    downloading: (p) => `Downloading ${p}%`,
    cancelDownload: 'Cancel download',
    downloadFailed: 'Download failed. Check your network and try again.',
    wifiHint: 'Wi-Fi is recommended for the download.',
    deviceFit: {
      ok: 'This phone looks to have enough memory (an estimate, not tested).',
      tight: 'Memory on this phone may be tight; the system may close the app while it runs (an estimate, not tested).',
      too_small: 'This phone may not have enough memory; on-device AI is not recommended (an estimate, not tested).',
      unknown: 'Cannot tell whether this phone has enough memory.',
    },
    serverAddress: 'Server address',
    serverAddressHint: 'For example https://your-server. Use https on the internet; http is allowed on a local network.',
    apiKey: 'Access key (optional)',
    apiKeyHint: 'Stored in the system keychain, not with the normal settings.',
    modelName: 'Model name',
    testConnection: 'Test connection',
    testing: 'Testing…',
    testOk: 'Connection works.',
    testAuth: 'The server rejected the access key.',
    testUnreachable: 'Cannot reach the server. Check the address and your network.',
    testTimeout: 'The server took too long to answer.',
    testUnexpected: 'The server answered in an unexpected way.',
    urlProblems: {
      empty: 'Please enter the server address.',
      invalid: 'The address is not valid.',
      scheme: 'Only http or https is supported.',
      https_required: 'Addresses on the internet must use https, otherwise pictures and the key travel unencrypted.',
    },
    language: 'Language (interface, answers, speech and voice recognition)',
    speakResults: 'Read results aloud',
    voice: 'Voice',
    voicePrivacy: {
      on_device: 'Speech recognition runs on the phone.',
      maybe_cloud: 'Speech recognition for this language may use the system cloud service.',
      unavailable: 'Speech recognition is not available in this build; please use the buttons.',
    },
    safetyTitle: 'Please note',
    safetyBody:
      'This is an assistive tool whose descriptions are generated by AI. It is not a safety device and not a navigation tool. ' +
      'It can be wrong or miss things, and one picture cannot show that your surroundings are safe. ' +
      'It cannot replace your own judgment, a white cane, a guide dog, or help from other people. ' +
      'Do not rely on it where it is dangerous, such as when crossing roads, driving or climbing.',
  },
};
