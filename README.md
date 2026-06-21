# Pixiv 圖片搜尋 Telegram Bot

對Bot輸入 `/pixiv <關鍵詞>` 即可透過按鈕選擇張數與分級,搜尋並回傳Pixiv插畫。

## 設定步驟

### 1. 取得 Telegram Bot Token
1. Telegram搜尋 **@BotFather**
2. 輸入 `/newbot`,依指示設定Bot名稱與username
3. 複製BotFather回覆的Token

### 2. 取得 Pixiv refresh_token
```bash
pip install gppt
gppt login
```
用Pixiv帳號登入一次,複製終端機印出的 `refresh_token`。

### 3. 設定 token.env
```bash
cp token.env.example token.env
```
打開`token.env`填入剛才取得的兩個Token。

### 4. 安裝套件並執行
```bash
pip install -r requirements.txt
python bot.py
```

## 指令說明

| 指令 | 說明 |
|---|---|
| `/start` 或 `/help` | 顯示使用說明 |
| `/pixiv <關鍵詞>` | 搜尋插畫,跳出按鈕選張數與分級 |
| `/confirm18` | (僅私訊)完成一次性成年聲明,解鎖R-18選項 |

## 分級防護機制(請務必理解)

- **群組內**:無論是否完成過聲明,一律只提供全年齡內容,不會出現R-18按鈕。
- **私訊內**:
  - 預設只能選「全年齡」
  - 需先輸入 `/confirm18` 完成一次性聲明,才會解鎖「R-18」「全部(不分級)」按鈕
- 程式碼裡有雙重保險:即使callback資料被竄改偽造成r18/all,後端仍會二次檢查「是否為群組」與「是否已聲明」,不符合者強制視為全年齡處理。

> ⚠️ **這不是完美的年齡驗證機制**,僅是基本的使用門檻(類似多數成人網站的「我已滿18歲」聲明點擊),無法真正驗證使用者實際年齡。若這個Bot未來會公開給不特定多數人使用,建議自行評估法律風險,必要時加上更嚴謹的驗證方式或乾脆不提供R-18功能。

## 注意事項

- 本專案使用 `pixivpy3`(非官方、基於逆向工程的Pixiv API封裝),並非Pixiv官方授權方式,Pixiv若改版可能導致功能失效。
- 圖片透過Bot伺服器下載後再上傳給Telegram(因Pixiv圖片伺服器有Referer限制),如遇大量請求,需注意IP是否被Pixiv暫時限制。
- `confirmed_adults`、`pending_searches`、`seen_illust_cache` 均為記憶體暫存資料,**Bot重啟後會清空**,不會永久保存。

## 檔案結構
```
tg-pixiv-bot/
├── bot.py               # 主程式
├── token.env            # 你的Token(不要上傳到GitHub!)
├── token.env.example    # Token範例格式
├── .gitignore
├── requirements.txt
└── README.md
```
