import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { useKeepAwake } from 'expo-keep-awake';
import { router } from 'expo-router';
import { useCallback, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { zoomIn, zoomOut, zoomPercent, zoomReset } from '../camera/zoom';
import { createAnalyzeController, type AnalyzeController, type ControllerState } from '../controller/analyze';
import { STRINGS } from '../i18n/strings';
import { createImageEncoder } from '../image/encoder';
import { createProviderFactory } from '../providers';
import { localProvider } from '../providers/runtime';
import { useApp } from '../state/AppProvider';
import { useTheme } from '../ui/theme';
import { parseCommand, type VoiceCommand } from '../voice/commands';
import { createRecognizer } from '../voice/recognizer';
import { createSpeaker } from '../voice/speaker';

export default function MainScreen() {
  useKeepAwake();
  const theme = useTheme();
  const { ready, settings, update, getSettings, getApiKey } = useApp();
  const t = STRINGS[settings.language];
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [zoom, setZoomState] = useState(0);
  const zoomRef = useRef(0);
  const [state, setState] = useState<ControllerState>({ phase: 'idle' });
  const [notice, setNotice] = useState('');
  const [heard, setHeard] = useState('');
  const [listening, setListening] = useState(false);

  const speaker = useMemo(() => createSpeaker(), []);
  const recognizer = useMemo(() => createRecognizer(), []);
  // Created on first use (inside an event handler), never during render: it captures refs and long-lived callbacks.
  const controllerRef = useRef<AnalyzeController | null>(null);
  const getController = useCallback((): AnalyzeController => {
    controllerRef.current ??= createAnalyzeController({
      getProvider: createProviderFactory({ getSettings, getApiKey, local: localProvider }),
      camera: {
        capture: async () => {
          const camera = cameraRef.current;
          if (!camera) throw new Error('The camera is not ready.');
          const picture = await camera.takePictureAsync({ quality: 0.7, shutterSound: false });
          return { uri: picture.uri, width: picture.width, height: picture.height };
        },
      },
      encoder: createImageEncoder(),
      speaker,
      getSettings: () => {
        const s = getSettings();
        return { language: s.language, speakResults: s.speakResults };
      },
      onState: setState,
    });
    return controllerRef.current;
  }, [getSettings, getApiKey, speaker]);

  const applyZoom = useCallback(
    (next: number, announce: boolean) => {
      zoomRef.current = next;
      setZoomState(next);
      void Haptics.selectionAsync();
      const s = getSettings();
      if (announce && s.speakResults) void speaker.speak(STRINGS[s.language].zoomLabel(zoomPercent(next)), s.language);
    },
    [getSettings, speaker],
  );

  const run = useCallback(
    async (command: VoiceCommand, viaVoice: boolean) => {
      const s = getSettings();
      switch (command.type) {
        case 'analyze':
          await getController().analyze();
          break;
        case 'zoom_in':
          applyZoom(zoomIn(zoomRef.current), viaVoice);
          break;
        case 'zoom_out':
          applyZoom(zoomOut(zoomRef.current), viaVoice);
          break;
        case 'zoom_reset':
          applyZoom(zoomReset(), viaVoice);
          break;
        case 'repeat':
          await getController().repeat();
          break;
        case 'stop':
          getController().stopSpeaking();
          break;
        case 'language':
          await update({ language: command.language });
          void speaker.speak(STRINGS[command.language].languageChanged, command.language);
          break;
        case 'unknown':
          setNotice(STRINGS[s.language].notUnderstood);
          if (s.speakResults) void speaker.speak(STRINGS[s.language].notUnderstoodShort, s.language);
          break;
      }
    },
    [getSettings, getController, applyZoom, update, speaker],
  );

  const pressed = useRef(false);
  const listeningRef = useRef(false);
  const lastText = useRef('');

  const startListening = useCallback(async () => {
    pressed.current = true;
    getController().stopSpeaking();
    setNotice('');
    if (!recognizer.isAvailable()) {
      setNotice(STRINGS[getSettings().language].speechUnavailable);
      return;
    }
    if (!(await recognizer.requestPermission())) {
      setNotice(STRINGS[getSettings().language].micDenied);
      return;
    }
    if (!pressed.current) return; // released while the permission prompt was open
    lastText.current = '';
    setHeard('');
    listeningRef.current = true;
    setListening(true);
    recognizer.start(getSettings().language, {
      onPartial: (text) => {
        lastText.current = text;
        setHeard(text);
      },
      onFinal: (text) => {
        lastText.current = text;
        setHeard(text);
      },
      onError: (code) => {
        if (code === 'not-allowed' || code === 'service-not-allowed') {
          setNotice(STRINGS[getSettings().language].micDenied);
        }
      },
      onEnd: () => {
        listeningRef.current = false;
        setListening(false);
        const text = lastText.current.trim();
        lastText.current = '';
        if (text) void run(parseCommand(text), true);
      },
    });
  }, [getSettings, getController, recognizer, run]);

  const stopListening = useCallback(() => {
    pressed.current = false;
    // A ref, not state: the button can be released before the re-render that sets `listening`.
    if (listeningRef.current) recognizer.stop();
  }, [recognizer]);

  if (!ready) return <View style={[styles.fill, { backgroundColor: theme.bg }]} />;

  if (!permission?.granted) {
    return (
      <SafeAreaView style={[styles.fill, styles.center, { backgroundColor: theme.bg }]}>
        <Text style={[styles.body, { color: theme.text }]}>{t.cameraDenied}</Text>
        <Pressable accessibilityRole="button" onPress={() => void requestPermission()} style={[styles.bigButton, { backgroundColor: theme.primary }]}>
          <Text style={[styles.bigButtonText, { color: theme.primaryText }]}>{t.allowCamera}</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const busy = state.phase === 'capturing' || state.phase === 'thinking';
  const modeLabel = settings.mode === 'local' ? t.modeLocal : t.modeRemote;

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: theme.bg }]} edges={['top', 'bottom']}>
      <View style={styles.topBar}>
        <View
          accessible
          accessibilityLabel={modeLabel}
          style={[styles.badge, { borderColor: settings.mode === 'remote' ? theme.warn : theme.border }]}
        >
          <Text style={{ color: settings.mode === 'remote' ? theme.warn : theme.text, fontWeight: '600' }}>{modeLabel}</Text>
        </View>
        <Text style={{ color: theme.muted }}>{t.zoomLabel(zoomPercent(zoom))}</Text>
        <Pressable accessibilityRole="button" accessibilityLabel={t.settings} onPress={() => router.push('/settings')} style={styles.smallButton}>
          <Text style={{ color: theme.primary, fontSize: 16, fontWeight: '600' }}>{t.settings}</Text>
        </Pressable>
      </View>
      {settings.mode === 'remote' && (
        <Text accessibilityRole="alert" style={[styles.warning, { color: theme.warn }]}>
          {t.remoteWarning}
        </Text>
      )}

      <View style={styles.cameraBox}>
        <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" zoom={zoom} />
        {busy && (
          <View style={styles.overlay}>
            <Text style={styles.overlayText}>{state.phase === 'capturing' ? t.capturing : t.thinking}</Text>
          </View>
        )}
      </View>

      <ScrollView style={styles.result} contentContainerStyle={{ padding: 12, gap: 8 }}>
        {listening || heard ? (
          <Text style={{ color: theme.muted }}>
            {listening ? t.listening : t.heard}
            {heard ? `: ${heard}` : ''}
          </Text>
        ) : null}
        {notice ? <Text style={{ color: theme.warn }}>{notice}</Text> : null}
        {state.phase === 'error' && (
          <Text accessibilityRole="alert" style={[styles.body, { color: theme.danger }]}>
            {state.message}
          </Text>
        )}
        {state.phase === 'done' && (
          <View style={[styles.card, { backgroundColor: theme.card, borderColor: state.plan.alert ? theme.warn : theme.border }]}>
            {state.plan.alert && <Text style={[styles.alert, { color: theme.warn }]}>{state.plan.alert}</Text>}
            <Text style={[styles.body, { color: theme.text }]}>
              {state.plan.descriptionWithheld ? '' : state.plan.description}
            </Text>
            {state.plan.uncertainty && <Text style={{ color: theme.muted }}>{state.plan.uncertainty}</Text>}
            <Text style={{ color: theme.muted, fontSize: 12 }}>
              {t.providerLabel[state.provider]} · {t.elapsed(state.latencyMs / 1000)}
            </Text>
          </View>
        )}
        <Text style={{ color: theme.muted, fontSize: 12 }}>{t.disclaimerShort}</Text>
      </ScrollView>

      <View style={styles.controls}>
        <View style={styles.row}>
          <SmallButton label={t.zoomOut} onPress={() => applyZoom(zoomOut(zoomRef.current), false)} theme={theme} />
          <SmallButton label={t.zoomReset} onPress={() => applyZoom(zoomReset(), false)} theme={theme} />
          <SmallButton label={t.zoomIn} onPress={() => applyZoom(zoomIn(zoomRef.current), false)} theme={theme} />
          <SmallButton label={t.repeat} onPress={() => void getController().repeat()} theme={theme} />
          <SmallButton label={t.stop} onPress={() => getController().stopSpeaking()} theme={theme} />
        </View>
        <View style={styles.row}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t.analyze}
            disabled={busy}
            onPress={() => void getController().analyze()}
            style={[styles.bigButton, { flex: 1, backgroundColor: busy ? theme.border : theme.primary }]}
          >
            <Text style={[styles.bigButtonText, { color: theme.primaryText }]}>{t.analyze}</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t.holdToTalk}
            accessibilityHint={t.notUnderstood}
            onPressIn={() => void startListening()}
            onPressOut={stopListening}
            style={[styles.bigButton, { flex: 1, backgroundColor: listening ? theme.danger : theme.card, borderWidth: 2, borderColor: theme.primary }]}
          >
            <Text style={[styles.bigButtonText, { color: listening ? theme.primaryText : theme.primary }]}>
              {listening ? t.releaseToSend : t.holdToTalk}
            </Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

function SmallButton({ label, onPress, theme }: { label: string; onPress: () => void; theme: ReturnType<typeof useTheme> }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.smallBtn, { backgroundColor: theme.card, borderColor: theme.border }]}
    >
      <Text style={{ color: theme.text, fontWeight: '600' }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', padding: 24, gap: 16 },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 6 },
  badge: { borderWidth: 1, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 4 },
  smallButton: { paddingHorizontal: 10, paddingVertical: 8, minHeight: 44, justifyContent: 'center' },
  warning: { paddingHorizontal: 12, paddingBottom: 4, fontSize: 13 },
  cameraBox: { height: 280, marginHorizontal: 12, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000' },
  overlay: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.45)', alignItems: 'center', justifyContent: 'center' },
  overlayText: { color: '#fff', fontSize: 20, fontWeight: '600' },
  result: { flex: 1 },
  card: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 6 },
  alert: { fontSize: 18, fontWeight: '700' },
  body: { fontSize: 17, lineHeight: 24 },
  controls: { padding: 12, gap: 10 },
  row: { flexDirection: 'row', gap: 8 },
  smallBtn: { flex: 1, minHeight: 44, borderWidth: 1, borderRadius: 10, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  bigButton: { minHeight: 64, borderRadius: 14, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  bigButtonText: { fontSize: 20, fontWeight: '700' },
});
