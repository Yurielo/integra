# Integra: пользовательский процесс

1. Откройте `Integra.app`, выберите **Projects & Sources**, нажмите **Choose
   video or audio** и выберите AAC, AIFF, FLAC, M4A, MP3, OGG, WAV, M4V, MKV,
   MOV, MP4 или WebM. Integra создаст проект, скопирует и проверит файл по
   SHA-256; исходник не изменяется.
2. Откройте **Transcript & Topics** и нажимайте **Refresh project result**.
   Локальные `ffmpeg` и `whisper-cli` готовят аудио и расшифровку. Модель по
   умолчанию — `~/whisper-models/ggml-large-v3.bin`; иной путь задаётся
   `INTEGRA_WHISPER_MODEL`.
3. В **Operations & Diagnostics** нажатие отменяет текущее задание; для
   отменённого или ошибочного задания повторное нажатие запускает безопасное
   возобновление из Integra-копии.
4. Проверьте **Transcript & Topics**, **Knowledge**, **Media** и **Exact
   Navigation**. Расшифровка помечена `MACHINE_TRANSCRIPT_UNREVIEWED`, темы и
   знания — `REVIEW_REQUIRED/PROVISIONAL`; машинный результат не принимается
   автоматически.
5. Для Obsidian откройте **Obsidian Export**, выберите Vault, проверьте preview
   и подтвердите Publish. Package выбирается из проекта автоматически; запись
   идёт только в управляемое поддерево `Integra/<project>/`.
6. Для OneDrive откройте **OneDrive Publication**, выберите локальную папку
   OneDrive, проверьте preview и подтвердите Publish. Это файловая публикация:
   `cloud_verified` остаётся `false`, Microsoft Graph и аккаунт не используются.

Данные находятся в `~/Library/Application Support/Integra`: проекты, копии
источников, состояния заданий, расшифровки и packages.
