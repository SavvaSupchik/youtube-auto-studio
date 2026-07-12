/**
 * Справочный каталог голосов Kokoro-82M по языкам.
 *
 * Схема ID: {язык}{пол}_{имя} — первая буква язык, вторая f=female/m=male.
 * Список собран из публичной документации модели Kokoro; конкретный набор
 * голосов может меняться между версиями модели — если какого-то ID не
 * окажется при синтезе, ошибка будет видна сразу в логе/при "Прослушать".
 */
export interface KokoroVoiceRef {
  language: string;
  voice_id: string;
  gender: "f" | "m";
}

export const KOKORO_VOICES: KokoroVoiceRef[] = [
  // American English
  { language: "en", voice_id: "af_heart", gender: "f" },
  { language: "en", voice_id: "af_alloy", gender: "f" },
  { language: "en", voice_id: "af_aoede", gender: "f" },
  { language: "en", voice_id: "af_bella", gender: "f" },
  { language: "en", voice_id: "af_jessica", gender: "f" },
  { language: "en", voice_id: "af_kore", gender: "f" },
  { language: "en", voice_id: "af_nicole", gender: "f" },
  { language: "en", voice_id: "af_nova", gender: "f" },
  { language: "en", voice_id: "af_river", gender: "f" },
  { language: "en", voice_id: "af_sarah", gender: "f" },
  { language: "en", voice_id: "af_sky", gender: "f" },
  { language: "en", voice_id: "am_adam", gender: "m" },
  { language: "en", voice_id: "am_echo", gender: "m" },
  { language: "en", voice_id: "am_eric", gender: "m" },
  { language: "en", voice_id: "am_fenrir", gender: "m" },
  { language: "en", voice_id: "am_liam", gender: "m" },
  { language: "en", voice_id: "am_michael", gender: "m" },
  { language: "en", voice_id: "am_onyx", gender: "m" },
  { language: "en", voice_id: "am_puck", gender: "m" },
  { language: "en", voice_id: "am_santa", gender: "m" },
  // British English (тоже язык "en" — Kokoro различает их внутри каталога)
  { language: "en", voice_id: "bf_alice", gender: "f" },
  { language: "en", voice_id: "bf_emma", gender: "f" },
  { language: "en", voice_id: "bf_isabella", gender: "f" },
  { language: "en", voice_id: "bf_lily", gender: "f" },
  { language: "en", voice_id: "bm_daniel", gender: "m" },
  { language: "en", voice_id: "bm_fable", gender: "m" },
  { language: "en", voice_id: "bm_george", gender: "m" },
  { language: "en", voice_id: "bm_lewis", gender: "m" },
  // Spanish
  { language: "es", voice_id: "ef_dora", gender: "f" },
  { language: "es", voice_id: "em_alex", gender: "m" },
  { language: "es", voice_id: "em_santa", gender: "m" },
  // French
  { language: "fr", voice_id: "ff_siwis", gender: "f" },
  // Italian
  { language: "it", voice_id: "if_sara", gender: "f" },
  { language: "it", voice_id: "im_nicola", gender: "m" },
  // Portuguese (brazilian)
  { language: "pt", voice_id: "pf_dora", gender: "f" },
  { language: "pt", voice_id: "pm_alex", gender: "m" },
  { language: "pt", voice_id: "pm_santa", gender: "m" },
  // Japanese
  { language: "ja", voice_id: "jf_alpha", gender: "f" },
  { language: "ja", voice_id: "jf_gongitsune", gender: "f" },
  { language: "ja", voice_id: "jf_nezumi", gender: "f" },
  { language: "ja", voice_id: "jf_tebukuro", gender: "f" },
  { language: "ja", voice_id: "jm_kumo", gender: "m" },
  // Mandarin Chinese
  { language: "zh", voice_id: "zf_xiaobei", gender: "f" },
  { language: "zh", voice_id: "zf_xiaoni", gender: "f" },
  { language: "zh", voice_id: "zf_xiaoxiao", gender: "f" },
  { language: "zh", voice_id: "zf_xiaoyi", gender: "f" },
  { language: "zh", voice_id: "zm_yunjian", gender: "m" },
  { language: "zh", voice_id: "zm_yunxi", gender: "m" },
  { language: "zh", voice_id: "zm_yunxia", gender: "m" },
  { language: "zh", voice_id: "zm_yunyang", gender: "m" },
  // Hindi
  { language: "hi", voice_id: "hf_alpha", gender: "f" },
  { language: "hi", voice_id: "hf_beta", gender: "f" },
  { language: "hi", voice_id: "hm_omega", gender: "m" },
  { language: "hi", voice_id: "hm_psi", gender: "m" },
  // Russian — у Kokoro нет нативной модели, используется английский голос как workaround
  { language: "ru", voice_id: "af_heart", gender: "f" },
  { language: "ru", voice_id: "am_michael", gender: "m" },
];
