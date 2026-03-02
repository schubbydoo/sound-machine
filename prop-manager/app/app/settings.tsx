import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  SafeAreaView,
  Alert,
} from 'react-native';
import { router } from 'expo-router';
import * as SecureStore from 'expo-secure-store';
import { usePropStore } from '../store/propStore';
import { SECURE_STORE_KEY_ACCESS_CODE } from '../constants/config';

export default function SettingsScreen() {
  const { accessCode, setAccessCode } = usePropStore();
  const [draft, setDraft] = useState(accessCode);

  useEffect(() => {
    SecureStore.getItemAsync(SECURE_STORE_KEY_ACCESS_CODE).then((val) => {
      if (val) {
        setDraft(val);
        setAccessCode(val);
      }
    });
  }, []);

  const save = async () => {
    await SecureStore.setItemAsync(SECURE_STORE_KEY_ACCESS_CODE, draft);
    setAccessCode(draft);
    Alert.alert('Saved', 'Access code saved securely.');
    router.back();
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
            <Text style={styles.backText}>‹ Back</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Settings</Text>
          <View style={{ width: 60 }} />
        </View>

        <View style={styles.section}>
          <Text style={styles.label}>Access Code</Text>
          <Text style={styles.hint}>
            Must match the access_code in /etc/propmanager/config.json on each prop.
          </Text>
          <TextInput
            style={styles.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="Enter access code"
            placeholderTextColor="#718096"
            autoCapitalize="none"
            autoCorrect={false}
            secureTextEntry
          />
        </View>

        <TouchableOpacity style={styles.saveBtn} onPress={save}>
          <Text style={styles.saveBtnText}>Save</Text>
        </TouchableOpacity>

        <View style={styles.about}>
          <Text style={styles.aboutText}>Prop Manager v1.0.0</Text>
          <Text style={styles.aboutText}>Backstage WiFi configuration tool</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f1117',
  },
  container: {
    flex: 1,
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 32,
  },
  backBtn: {
    width: 60,
  },
  backText: {
    color: '#4299e1',
    fontSize: 18,
  },
  title: {
    color: '#e2e8f0',
    fontSize: 20,
    fontWeight: '700',
  },
  section: {
    marginBottom: 24,
  },
  label: {
    color: '#e2e8f0',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 6,
  },
  hint: {
    color: '#718096',
    fontSize: 12,
    marginBottom: 10,
    lineHeight: 18,
  },
  input: {
    backgroundColor: '#1a202c',
    color: '#e2e8f0',
    borderRadius: 8,
    padding: 14,
    fontSize: 15,
    borderWidth: 1,
    borderColor: '#2d3748',
  },
  saveBtn: {
    backgroundColor: '#3182ce',
    borderRadius: 8,
    padding: 16,
    alignItems: 'center',
  },
  saveBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 16,
  },
  about: {
    marginTop: 'auto',
    alignItems: 'center',
    paddingBottom: 16,
  },
  aboutText: {
    color: '#4a5568',
    fontSize: 13,
  },
});
