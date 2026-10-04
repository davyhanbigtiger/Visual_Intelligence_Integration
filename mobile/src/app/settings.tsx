import * as Device from 'expo-device';
import { router } from 'expo-router';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { Language, ProviderId } from '../core/types';
import { STRINGS } from '../i18n/strings';
import { SETTINGS_STRINGS } from '../i18n/settingsStrings';
import { deviceFit, downloadModel, modelStatus } from '../providers/localModel';
import { nativeModelFiles } from '../providers/nativeModelFiles';
import { testConnection, type ConnectionCheck } from '../providers/remote';
import { useApp } from '../state/AppProvider';
import { normalizeRemoteUrl } from '../settings/validate';
import { useTheme, type Theme } from '../ui/theme';
import { createRecognizer, type SpeechPrivacy } from '../voice/recognizer';

export default function SettingsScreen() {
  const theme = useTheme();
  const app = useApp();
  const { settings } = app;
  const t = STRINGS[settings.language];
  const s = SETTINGS_STRINGS[settings.language];

  const [urlText, setUrlText] = useState(settings.remoteUrl);
  const [keyText, setKeyText] = useState(app.apiKey);
  const [modelText, setModelText] = useState(settings.remoteModel);
  const [test, setTest] = useState<'idle' | 'running' | ConnectionCheck>('idle');
  const [status, setStatus] = useState(() => modelStatus(nativeModelFiles));
  const [progress, setProgress] = useState<number | null>(null);
  const [downloadError, setDownloadError] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const [privacy, setPrivacy] = useState<SpeechPrivacy>('unavailable');
  const recognizer = useMemo(() => createRecognizer(), []);

  useEffect(() => {
    let alive = true;
    void recognizer.privacy(settings.language).then((p) => alive && setPrivacy(p));
    return () => {
      alive = false;
    };
  }, [recognizer, settings.language]);

  const urlCheck = normalizeRemoteUrl(urlText);

  const chooseEngine = (mode: ProviderId) => {
    if (mode === 'local') {
      void app.update({ mode: 'local' });
      return;
    }
    if (settings.remoteConsent) {
      void app.update({ mode: 'remote' });
      return;
    }
    Alert.alert(t.remoteConsentTitle, t.remoteConsentBody, [
      { text: t.cancel, style: 'cancel' },
      { text: t.agree, onPress: () => void app.update({ mode: 'remote', remoteConsent: true }) },
    ]);
  };

  const runTest = async () => {
    if (!urlCheck.ok) return;
    setTest('running');
    setTest(await testConnection(urlCheck.url, keyText.trim() || undefined));
  };

  const startDownload = async () => {
    setDownloadError('');
    setProgress(0);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await downloadModel(nativeModelFiles, setProgress, controller.signal);
    } catch {
      if (!controller.signal.aborted) setDownloadError(s.downloadFailed);
    } finally {
      abortRef.current = null;
      setProgress(null);
      setStatus(modelStatus(nativeModelFiles));
    }
  };

  const testMessage = (): string => {
    if (test === 'idle') return '';
    if (test === 'running') return s.testing;
    if (test.ok) return s.testOk;
    return { auth: s.testAuth, unreachable: s.testUnreachable, timeout: s.testTimeout, unexpected: s.testUnexpected, ok: s.testOk }[test.detail];
  };

  const modelLine = status.ready ? s.modelReady : status.main === 'partial' || status.mmproj === 'partial' ? s.modelPartial : s.modelMissing;
  const fit = deviceFit(Device.totalMemory ?? null);

  return (
    <SafeAreaView style={[styles.fill, { backgroundColor: theme.bg }]} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel={t.back} onPress={() => router.back()} style={styles.back}>
          <Text style={{ color: theme.primary, fontSize: 17, fontWeight: '600' }}>{t.back}</Text>
        </Pressable>
        <Text accessibilityRole="header" style={[styles.title, { color: theme.text }]}>
          {s.title}
        </Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Section title={s.engine} theme={theme}>
          <Segmented
            theme={theme}
            value={settings.mode}
            options={[
              { value: 'local', label: s.local },
              { value: 'remote', label: s.remote },
            ]}
            onChange={chooseEngine}
          />
          <Text style={{ color: theme.muted }}>{settings.mode === 'local' ? s.localHelp : s.remoteHelp}</Text>
        </Section>

        <Section title={s.model} theme={theme}>
          <Text style={{ color: theme.text }}>{modelLine}</Text>
          <Text style={{ color: theme.muted }}>{s.deviceFit[fit]}</Text>
          {progress === null ? (
            !status.ready && (
              <>
                <Text style={{ color: theme.muted }}>{s.wifiHint}</Text>
                <Button label={s.download} onPress={() => void startDownload()} theme={theme} />
              </>
            )
          ) : (
            <>
              <View style={[styles.track, { backgroundColor: theme.border }]}>
                <View style={[styles.fillBar, { backgroundColor: theme.primary, width: `${Math.round(progress * 100)}%` }]} />
              </View>
              <Text style={{ color: theme.text }}>{s.downloading(Math.round(progress * 100))}</Text>
              <Button label={s.cancelDownload} onPress={() => abortRef.current?.abort()} theme={theme} secondary />
            </>
          )}
          {downloadError ? <Text style={{ color: theme.danger }}>{downloadError}</Text> : null}
        </Section>

        <Section title={s.remote} theme={theme}>
          <Field label={s.serverAddress} theme={theme}>
            <TextInput
              value={urlText}
              onChangeText={(text) => {
                setUrlText(text);
                // Saved as you type: onEndEditing alone lost the address when you left the screen with the field still focused.
                void app.update({ remoteUrl: text });
              }}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              placeholder="https://"
              placeholderTextColor={theme.muted}
              style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.card }]}
            />
          </Field>
          <Text style={{ color: urlCheck.ok || urlText.trim() === '' ? theme.muted : theme.danger }}>
            {urlCheck.ok || urlText.trim() === '' ? s.serverAddressHint : s.urlProblems[urlCheck.reason]}
          </Text>
          <Field label={s.apiKey} theme={theme}>
            <TextInput
              value={keyText}
              onChangeText={(text) => {
                setKeyText(text);
                void app.setApiKey(text);
              }}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.card }]}
            />
          </Field>
          <Text style={{ color: theme.muted }}>{s.apiKeyHint}</Text>
          <Field label={s.modelName} theme={theme}>
            <TextInput
              value={modelText}
              onChangeText={(text) => {
                setModelText(text);
                void app.update({ remoteModel: text });
              }}
              autoCapitalize="none"
              autoCorrect={false}
              style={[styles.input, { color: theme.text, borderColor: theme.border, backgroundColor: theme.card }]}
            />
          </Field>
          <Button label={s.testConnection} onPress={() => void runTest()} theme={theme} secondary disabled={!urlCheck.ok || test === 'running'} />
          {test !== 'idle' && <Text style={{ color: test !== 'running' && !test.ok ? theme.danger : theme.text }}>{testMessage()}</Text>}
        </Section>

        <Section title={s.language} theme={theme}>
          <Segmented
            theme={theme}
            value={settings.language}
            options={[
              { value: 'zh', label: '中文' },
              { value: 'en', label: 'English' },
            ]}
            onChange={(language: Language) => void app.update({ language })}
          />
        </Section>

        <Section title={s.voice} theme={theme}>
          <View style={styles.switchRow}>
            <Text style={{ color: theme.text, flex: 1 }}>{s.speakResults}</Text>
            <Switch value={settings.speakResults} onValueChange={(speakResults) => void app.update({ speakResults })} />
          </View>
          <Text style={{ color: theme.muted }}>{s.voicePrivacy[privacy]}</Text>
        </Section>

        <Section title={s.safetyTitle} theme={theme}>
          <Text style={{ color: theme.text, lineHeight: 22 }}>{s.safetyBody}</Text>
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, children, theme }: { title: string; children: React.ReactNode; theme: Theme }) {
  return (
    <View style={[styles.section, { backgroundColor: theme.card, borderColor: theme.border }]}>
      <Text accessibilityRole="header" style={[styles.sectionTitle, { color: theme.text }]}>
        {title}
      </Text>
      {children}
    </View>
  );
}

function Field({ label, children, theme }: { label: string; children: React.ReactNode; theme: Theme }) {
  return (
    <View style={{ gap: 4 }}>
      <Text style={{ color: theme.muted, fontSize: 13 }}>{label}</Text>
      {children}
    </View>
  );
}

function Button({ label, onPress, theme, secondary, disabled }: { label: string; onPress: () => void; theme: Theme; secondary?: boolean; disabled?: boolean }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[
        styles.button,
        secondary ? { borderWidth: 1, borderColor: theme.primary } : { backgroundColor: theme.primary },
        disabled ? { opacity: 0.45 } : null,
      ]}
    >
      <Text style={{ color: secondary ? theme.primary : theme.primaryText, fontSize: 16, fontWeight: '700' }}>{label}</Text>
    </Pressable>
  );
}

function Segmented<T extends string>({
  options,
  value,
  onChange,
  theme,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  theme: Theme;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Pressable
            key={option.value}
            accessibilityRole="button"
            accessibilityState={{ selected }}
            accessibilityLabel={option.label}
            onPress={() => onChange(option.value)}
            style={[
              styles.segment,
              { borderColor: theme.primary, backgroundColor: selected ? theme.primary : 'transparent' },
            ]}
          >
            <Text style={{ color: selected ? theme.primaryText : theme.primary, fontWeight: '700' }}>{option.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 8, paddingVertical: 4 },
  back: { minWidth: 72, minHeight: 44, justifyContent: 'center', paddingHorizontal: 8 },
  title: { fontSize: 20, fontWeight: '700' },
  content: { padding: 12, gap: 12 },
  section: { borderWidth: 1, borderRadius: 12, padding: 12, gap: 10 },
  sectionTitle: { fontSize: 17, fontWeight: '700' },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 16, minHeight: 44 },
  button: { minHeight: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  segmented: { flexDirection: 'row', gap: 8 },
  segment: { flex: 1, minHeight: 48, borderWidth: 2, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  track: { height: 10, borderRadius: 5, overflow: 'hidden' },
  fillBar: { height: 10 },
});
