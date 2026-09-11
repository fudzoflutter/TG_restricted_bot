
# Telegram DialogSpyBot (not original ofc)

[English](#instruction) | [Русский](#инструкция)

---

## Instruction

### Table of Contents
1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Settings](#4-settings)
5. [Extras](#5-extras)

---

### 1. Overview

I’m 100% sure you’ve come across dozen of Telegram bots that offer for a nominal fee (in Stars or fiat—it doesn’t matter) the ability to save messages that your chat partner deletes from your chat with them. Why throw money at such a brain-dead feature? You could easily run this dead-simple script yourself or literally just use [AyuGram](https://github.com/ayugram). **Stop funding these grifters!!!!**

This script can help with:
* Recovering deleted messages (and edited messages)
* Saving self-destructing media (voice/video messages, photos, and videos)
* Organizing all of the above by chat (so you don't get confused)

---

### 2. Installation


    git clone https://github.com/your-username/DialogSpyBot.git
    cd DialogSpyBot
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python bot.py

---
### 3. Configuration

1. Environment Variables (.env)
Create a .env file in the project root:
`BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` 
`MY_USER_ID=123456789`
`DB_PATH=messages_cache.db`

2. Telegram Setup
Open [@BotFather](https://t.me/BotFather) and enable business and threaded mode for your bot.
Go to Telegram Settings -> My Profile -> Edit -> Chat Automation and connect your bot. (give permission only to manage messages)
Start a direct chat with your bot and send `/start`.
---
### 4. Settings

Run `/settings` in DM to configure:

**👤 Message Header** Toggle First Name, Last Name, @username, and User ID.
**🧵 DM Topics**: Enable/disable separate forum threads for each contact.
**📥 Media Saving Mode**: Save on trigger (!, +, save) or on any text reply (default).
**🌐 Language**: Switch between English and Russian.

---
#### 5. Extras
Please note that using this script violates the Telegram API Terms of Service (Section 1.4) and may result in your account being blocked. 
By using this script, you fully acknowledge that you are aware of the possible consequences and are acting at your own risk.

---
## Инструкция


### Оглавление

1. [Описание](#1-описание)
2. [Установка](#2-установка)
3. [Конфигурация](#3-конфигурация)
4. [Настройки](#4-настройки)
5. [Дополнительно](#5-дополнительно)

---
### 1. Описание


Я на 100 % уверен, что вы встречали десятки ботов в Telegram, которые за символическую плату (в «звездах» или деньгах — не суть) предлагают возможность сохранять сообщения, которые ваш собеседник удаляет из вашего чата с ним. Зачем платить за настолько банальную функцию, если можно либо самостоятельно запустить этот до жути простой скрипт, либо просто воспользоваться [AyuGram](https://github.com/ayugram)? Хватит отдавать деньги не пойми за что!!!!

Данный скрипт позволит вам:
* Фиксировать удаленные сообщения (и редактирование сообщений)
* Сохранять самоуничтожающиеся медиа (голосовые/видео сообщения, фото и видео)
* Группировать все вышеперечисленное по чатам (чтобы не запутаться)

---

### 2. Установка

    git clone https://github.com/your-username/DialogSpyBot.git
    cd DialogSpyBot
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    python bot.py

---
### 3. Конфигурация

1. Переменные окружения (.env)
Создайте файл .env в корне проекта:
`BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`
`MY_USER_ID=123456789`
`DB_PATH=messages_cache.db`
2. Подключение к Telegram
В [@BotFather](https://t.me/BotFather) включите Business и Threaded mode 
В клиенте Telegram перейдите в Настройки -> Изм. (Изменить) -> Автоматизация чатов (достаточно будет разрешений только на сообщения).
Откройте диалог с ботом и отправьте `/start`.

---
### 4. Настройки

Команда `/settings` открывает панель управления:

**👤 Заголовок сообщения**: переключение показа имени, фамилии, @username и User ID.
**🧵 Темы в ЛС**: включение/выключение создания отдельных веток под каждого пользователя.
**📥 Сохранение медиа**: по триггеру (!, +, save) или на любой ваш ответ.
**🌐 Язык**: переключение между русским и английским интерфейсом.

---

#### 5. Дополнительно
Примите во внимание, что использование данного скрипта нарушает Telegram API Terms of Service (пункт 1.4) и может караться блокировкой аккаунта. Использование скрипта означает ваше полное согласие с тем, что вы осознаете возможные последствия и действуете под свою личную ответственность (на свой страх и риск)

P.S.: Уважаемые пользователи, подразумевается, что раз вы и так пользуетесь Telegram, у вас есть работающие способы обхода региональных блокировок (далее СОРБ). Данный скрипт можно запустить (и он будет работать) на том же устройстве, где у вас работает СОРБ. В случае неполадок либо поиграйтесь с настройками вашего СОРБ либо смените его. В крайнем случае, можете арендовать дедик (VPS) никогда лишним не будет <3