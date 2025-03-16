import requests
from bs4 import BeautifulSoup
import telebot
import time
import threading
import configparser
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

# === Ввод данных для Telegram бота ===
API_TOKEN = '7534938653:AAEvgUzzN61MuQOk61HEteVRwHaPnZlNDuQ'
CHANNEL_ID = '@dsadsdsawewq'

# Инициализация бота
bot = telebot.TeleBot(API_TOKEN)

# URL страницы магазина с подарками
URL = 'https://market.tonnel.network/'  # Замени на URL магазина

# Настройки для Selenium
options = Options()
options.headless = True
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Глобальные переменные для управления ботом
paused = False
filters = {'name': set(), 'price': []}

# Инициализация configparser
config = configparser.ConfigParser()
config_file_path = '/Users/maximholodov/Desktop/Telegram Bots/Test New/config.ini'

# Создание и чтение файла конфигурации
if not os.path.exists(config_file_path):
    with open(config_file_path, 'w') as configfile:
        config['Gifts'] = {}
        config['Mute'] = {}
        config['PriceFilter'] = {}
        config.write(configfile)
        print(f"Created new config file at {config_file_path}")
else:
    config.read(config_file_path)
    print(f"Read existing config file from {config_file_path}")

# Убедимся, что разделы 'Gifts', 'Mute' и 'PriceFilter' существуют
if 'Gifts' not in config:
    config['Gifts'] = {}
if 'Mute' not in config:
    config['Mute'] = {}
if 'PriceFilter' not in config:
    config['PriceFilter'] = {}

# Функция для парсинга страницы
def parse_page():
    driver.get(URL)
    time.sleep(5)  # Ждём, пока страница полностью загрузится
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Находим контейнер с подарками
    grid_container = soup.find('div', class_='grid w-full grid-cols-2 gap-2 p-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6')
    if not grid_container:
        print("Grid container not found")
        return []

    # Список для хранения информации о товарах
    gifts = []

    # Парсинг каждого подарка (ограничиваем до первых 10)
    for gift_div in grid_container.find_all('div', class_='rounded-lg border bg-card text-card-foreground shadow-sm relative w-full max-w-md')[:10]:
        try:
            name = gift_div.find('div', class_='font-semibold text-sm').text.strip()
            order_number = gift_div.find('div', class_='font-semibold text-muted-foreground text-xs').text.strip()
            price = gift_div.find('div', class_='flex items-center gap-1 visible').text.strip()
            gifts.append({'name': name, 'order_number': order_number, 'price': price})
        except AttributeError as e:
            print(f"Error parsing gift: {e}")
            continue
    return gifts

# Функция для отправки уведомлений в Telegram
def send_message(gift):
    if paused:
        print("Bot is paused. Skipping message sending.")
        return

    gift_name = gift['name'].replace(" ", "").replace("-", "")
    gift_link = f"https://t.me/nft/{gift_name}-{gift['order_number'][1:]}"
    message = f"🎁 Новый подарок найден!\n📌 Название: {gift['name']}\n🔢 Номер: {gift['order_number']}\n💰 Цена: {gift['price']} $TON\n🔗 Ссылка: {gift_link}"
    print(f"Attempting to send message: {message}")
    try:
        bot.send_message(CHANNEL_ID, message)
        print(f"Message sent: {message}")
    except telebot.apihelper.ApiTelegramException as e:
        print(f"Failed to send message: {e}")
        if e.result_json['error_code'] == 429:
            retry_after = int(e.result_json['parameters']['retry_after'])
            print(f"Retrying after {retry_after} seconds")
            bot.send_message(CHANNEL_ID, f"Rate limit exceeded. Retrying after {retry_after} seconds.")
            time.sleep(retry_after)
            send_message(gift)
        else:
            print(f"Error details: {e.result_json}")

# Команда для паузы
@bot.message_handler(commands=['pause'])
def pause_notifications(message):
    global paused
    paused = True
    bot.reply_to(message, "Уведомления приостановлены.")

# Команда для возобновления
@bot.message_handler(commands=['resume'])
def resume_notifications(message):
    global paused
    paused = False
    bot.reply_to(message, "Уведомления возобновлены.")

# Команда для настроек
@bot.message_handler(commands=['settings'])
def settings_menu(message):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(telebot.types.InlineKeyboardButton("Список фильтров", callback_data="filters_list_1"))
    markup.add(telebot.types.InlineKeyboardButton("Фильтр по цене", callback_data="filter_price"))
    markup.add(telebot.types.InlineKeyboardButton("Отключить все фильтры", callback_data="disable_all_filters"))
    bot.send_message(message.chat.id, "Настройки фильтрации:", reply_markup=markup)

# Функция для безопасного редактирования сообщения с учетом лимитов
def safe_edit_message_text(text, chat_id, message_id, reply_markup):
    retry_count = 0
    max_retries = 5
    while retry_count < max_retries:
        try:
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
            return
        except telebot.apihelper.ApiTelegramException as e:
            if e.result_json['error_code'] == 429:
                retry_after = int(e.result_json['parameters']['retry_after'])
                print(f"Retrying after {retry_after} seconds due to rate limit")
                bot.send_message(chat_id, f"Rate limit exceeded. Retrying after {retry_after} seconds.")
                time.sleep(retry_after)
                retry_count += 1
            else:
                raise e

# Обработчик на выбор фильтра
@bot.callback_query_handler(func=lambda call: call.data.startswith("filters_list_"))
def show_filters(call, page=None):
    if page is None:
        page = int(call.data.split("_")[-1])
    known_gifts = sorted([gift for gift in config['Gifts'].get('known_gifts', '').split(',') if len(gift) >= 2])
    muted_gifts = set(config['Mute'].get('muted_gifts', '').split(','))
    items_per_page = 7
    total_pages = (len(known_gifts) + items_per_page - 1) // items_per_page
    start = (page - 1) * items_per_page
    end = start + items_per_page
    gifts_on_page = known_gifts[start:end]

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)

    # Добавляем опцию "Все подарки"
    all_gifts_enabled = len(muted_gifts) == 0
    all_gifts_button_text = "✅" if all_gifts_enabled else "☑️"
    markup.add(
        telebot.types.InlineKeyboardButton("Все подарки", callback_data="toggle_all_gifts"),
        telebot.types.InlineKeyboardButton(all_gifts_button_text, callback_data="toggle_all_gifts")
    )

    for gift in gifts_on_page:
        enabled = gift not in muted_gifts
        button_text = "✅" if enabled else "☑️"
        markup.add(
            telebot.types.InlineKeyboardButton(gift, callback_data=f"gift_{gift}"),
            telebot.types.InlineKeyboardButton(button_text, callback_data=f"toggle_{gift}_{page}")
        )

    # Добавляем кнопки для навигации по страницам
    nav_buttons = []
    if page > 1:
        nav_buttons.append(telebot.types.InlineKeyboardButton("⬅️", callback_data=f"filters_list_{page-1}"))
    if page < total_pages:
        nav_buttons.append(telebot.types.InlineKeyboardButton("➡️", callback_data=f"filters_list_{page+1}"))
    markup.add(*nav_buttons)

    # Добавляем кнопку "Назад"
    markup.add(telebot.types.InlineKeyboardButton("Назад", callback_data="back_to_settings"))
    safe_edit_message_text("Текущие фильтры:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

# Обработчик для переключения уведомлений
@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_notification(call):
    data = call.data.split("_")
    gift_name = "_".join(data[1:-1])
    page = int(data[-1])
    muted_gifts = set(config['Mute'].get('muted_gifts', '').split(','))
    if gift_name in muted_gifts:
        muted_gifts.remove(gift_name)
        bot.answer_callback_query(call.id, f"Уведомления для {gift_name} включены.")
    else:
        muted_gifts.add(gift_name)
        bot.answer_callback_query(call.id, f"Уведомления для {gift_name} отключены.")
    
    # Обновляем config.ini
    config['Mute']['muted_gifts'] = ','.join(muted_gifts)
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    
    show_filters(call, page)

# Обработчик для переключения всех уведомлений
@bot.callback_query_handler(func=lambda call: call.data == "toggle_all_gifts")
def toggle_all_gifts(call):
    known_gifts = set(config['Gifts'].get('known_gifts', '').split(','))
    muted_gifts = set(config['Mute'].get('muted_gifts', '').split(','))

    if len(muted_gifts) == 0:
        muted_gifts = known_gifts
        bot.answer_callback_query(call.id, "Уведомления для всех подарков отключены.")
    else:
        muted_gifts.clear()
        bot.answer_callback_query(call.id, "Уведомления для всех подарков включены.")

    # Обновляем config.ini
    config['Mute']['muted_gifts'] = ','.join(muted_gifts)
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    
    show_filters(call)

# Обработчик для фильтра по цене
@bot.callback_query_handler(func=lambda call: call.data == "filter_price")
def add_price_filter(call):
    min_price = config['PriceFilter'].get('min_price', None)
    max_price = config['PriceFilter'].get('max_price', None)
    if min_price and max_price:
        filter_status = f"Фильтр установлен от {min_price} до {max_price}"
    else:
        filter_status = "Фильтр не установлен"
    
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(telebot.types.InlineKeyboardButton("Указать минимальную цену (От)", callback_data="set_min_price"))
    markup.add(telebot.types.InlineKeyboardButton("Указать максимальную цену (До)", callback_data="set_max_price"))
    markup.add(telebot.types.InlineKeyboardButton("Назад", callback_data="back_to_settings"))
    bot.edit_message_text(filter_status, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "set_min_price")
def set_min_price(call):
    msg = bot.send_message(call.message.chat.id, "Укажите минимальную цену (От):")
    bot.register_next_step_handler(msg, save_min_price, call)

def save_min_price(message, call):
    min_price = message.text
    config['PriceFilter']['min_price'] = min_price
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    bot.send_message(call.message.chat.id, f"Минимальная цена установлена: {min_price}")
    add_price_filter(call)

@bot.callback_query_handler(func=lambda call: call.data == "set_max_price")
def set_max_price(call):
    msg = bot.send_message(call.message.chat.id, "Укажите максимальную цену (До):")
    bot.register_next_step_handler(msg, save_max_price, call)

def save_max_price(message, call):
    max_price = message.text
    config['PriceFilter']['max_price'] = max_price
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    bot.send_message(call.message.chat.id, f"Максимальная цена установлена: {max_price}")
    add_price_filter(call)

# Обработчик для отключения всех фильтров
@bot.callback_query_handler(func=lambda call: call.data == "disable_all_filters")
def disable_all_filters(call):
    filters['name'].clear()
    filters['price'].clear()
    config['Mute']['muted_gifts'] = ''
    config['PriceFilter']['min_price'] = '0'
    config['PriceFilter']['max_price'] = 'inf'
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    bot.answer_callback_query(call.id, "Все фильтры отключены.")
    back_to_settings(call)

# Обработчик для удаления фильтра
@bot.callback_query_handler(func=lambda call: call.data == "remove_filter")
def remove_filter_menu(call):
    if filters['name'] or filters['price']:
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        for f in filters['name']:
            markup.add(telebot.types.InlineKeyboardButton(f"Удалить {f}", callback_data=f"remove_name_{f}"))
        for p in filters['price']:
            markup.add(telebot.types.InlineKeyboardButton(f"Удалить От {p[0]} До {p[1]}", callback_data=f"remove_price_{p[0]}_{p[1]}"))
        markup.add(telebot.types.InlineKeyboardButton("Назад", callback_data="back_to_settings"))
        bot.edit_message_text("Выберите фильтр для удаления:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "Нет фильтров для удаления.")

# Обработчик для удаления фильтра
@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_name_"))
def remove_name_filter(call):
    filter_to_remove = call.data.replace("remove_name_", "")
    filters['name'].remove(filter_to_remove)
    bot.send_message(call.message.chat.id, f"Фильтр {filter_to_remove} удалён.")
    back_to_settings(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_price_"))
def remove_price_filter(call):
    _, min_price, max_price = call.data.split("_")
    filters['price'].remove((min_price, max_price))
    bot.send_message(call.message.chat.id, f"Фильтр по цене: От {min_price} До {max_price} удалён.")
    back_to_settings(call)

# Обработчик для кнопки "Назад"
@bot.callback_query_handler(func=lambda call: call.data == "back_to_settings")
def back_to_settings(call):
    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    markup.add(telebot.types.InlineKeyboardButton("Список фильтров", callback_data="filters_list_1"))
    markup.add(telebot.types.InlineKeyboardButton("Фильтр по цене", callback_data="filter_price"))
    markup.add(telebot.types.InlineKeyboardButton("Отключить все фильтры", callback_data="disable_all_filters"))
    bot.edit_message_text("Настройки фильтрации:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

# Команда для очистки config.ini
@bot.message_handler(commands=['clearconfig'])
def clear_config(message):
    config['Gifts'] = {}
    config['Mute'] = {}
    config['PriceFilter'] = {}
    with open(config_file_path, 'w') as configfile:
        config.write(configfile)
    bot.reply_to(message, "config.ini очищен.")

# Команда для отображения содержимого config.ini
@bot.message_handler(commands=['showconfig'])
def show_config(message):
    known_gifts = config['Gifts'].get('known_gifts', '')
    muted_gifts = config['Mute'].get('muted_gifts', '')
    min_price = config['PriceFilter'].get('min_price', 'не установлена')
    max_price = config['PriceFilter'].get('max_price', 'не установлена')
    response = "Записанные имена:\n"
    response += f"Известные подарки:\n{known_gifts.replace(',', '\n')}\n\n"
    response += f"Отключенные подарки:\n{muted_gifts.replace(',', '\n')}\n\n"
    response += f"Фильтр по цене:\nМинимальная цена: {min_price}\nМаксимальная цена: {max_price}"
    bot.send_message(message.chat.id, response)

# Основной цикл для парсинга и отправки сообщений
def parse_and_notify():
    known_gifts = set(config['Gifts'].get('known_gifts', '').split(',')) if 'known_gifts' in config['Gifts'] else set()
    muted_gifts = set(config['Mute'].get('muted_gifts', '').split(',')) if 'muted_gifts' in config['Mute'] else set()
    min_price = float(config['PriceFilter'].get('min_price', '0'))
    max_price = float(config['PriceFilter'].get('max_price', 'inf'))
    print("Bot started...")

    try:
        while True:
            if not paused:
                try:
                    gifts = parse_page()
                    print(f"Parsed {len(gifts)} gifts")

                    for gift in gifts:
                        name = gift['name']
                        print(f"Processing gift: {gift}")

                        if len(name) < 2:
                            print(f"Skipping gift {name} due to short name")
                            continue

                        if name in muted_gifts:
                            print(f"Skipping gift {name} as it is muted")
                            continue

                        # Применение фильтров
                        if name in filters['name']:
                            print(f"Skipping gift {name} due to name filter")
                            continue
                        price_value = float(gift['price'].replace(',', '.'))
                        if not (min_price <= price_value <= max_price):
                            print(f"Skipping gift {name} due to price filter: {price_value}")
                            continue

                        print(f"Sending message for gift: {gift}")
                        send_message(gift)

                        # Запись нового подарка в config.ini, если он новый
                        if name not in known_gifts:
                            known_gifts.add(name)
                            config['Gifts']['known_gifts'] = ','.join(known_gifts)
                            with open(config_file_path, 'w') as configfile:
                                config.write(configfile)
                            print(f"Updated config.ini with new gift: {name}")

                    time.sleep(3)  # Ждём 3 секунды перед следующим запросом
                except Exception as e:
                    print(f"Ошибка: {e}")
                    time.sleep(3)
            else:
                time.sleep(3)
    except KeyboardInterrupt:
        print("Программа завершена пользователем")
    finally:
        driver.quit()

# Запуск polling для обработки команд в отдельном потоке
if __name__ == '__main__':
    threading.Thread(target=bot.polling, kwargs={'none_stop': True}).start()
    parse_and_notify()
