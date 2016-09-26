#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import vk_api
import configparser
import re
import time
import os, sys
import argparse
import html
from pprint import pprint

import threading
import queue
from urllib.request import urlretrieve

# Local vars
keepcharacters = (' ', '.', '_', '—', '(', ')')
is_verbose = True
threads_num = 5
pause_sec = 15
sleep_every_tracknum = 200
output_path = './'
files_count = 0
is_only_downloadin = True


# ===============================================================================
# NB: Максимальное число альбомов для запроса - 100
# https://vk.com/dev/audio.getAlbums
# ===============================================================================
def parse(config_filename, out_filename):
    """ Загрузка альбомов в ini-файл """

    # Read config
    reader = configparser.ConfigParser()
    reader.read(config_filename)

    _user_id = reader.get('USER', 'id')
    _user_pass = reader.get('USER', 'pass')
    _user_login = reader.get('USER', 'login')

    vk_session = vk_api.VkApi(_user_login, _user_pass)
    config = configparser.ConfigParser()

    # Соединение с vk api
    try:
        vk_session.authorization()
    except vk_api.AuthorizationError as error_msg:
        print(error_msg)
        return

    vk = vk_session.get_api()
    albums = vk.audio.getAlbums(owner_id=_user_id, count=100) #NB!

    if (not albums):
        raise Exception('No albums loaded')

    # Подготовка файла
    config.read(out_filename)
    cfgfile = open(out_filename, 'w')
    ctn, file_count = 0, 0

    # Заполнить файл альбомами, которых ещё нет
    for album in albums['items']:
        aid, atitle = album['id'], album['title']
        album_sec = safe_fs_name(atitle)  # "%s | %s" % (atitle, aid)

        try:
            config.add_section(album_sec)
            is_verbose and print("> Добавлен %s" % atitle)

        except configparser.DuplicateSectionError as error_msg:
            is_verbose and print("> Пропуск %s" % atitle)

        # Заполнить альбом треками
        try:
            tracks = vk.audio.get(owner_id=_user_id, album_id=aid)
            for track in tracks['items']:
                trackname = "%s — %s" % (track['artist'], track['title'])

                # Пауза
                ctn += 1
                if sleep_every_tracknum < ctn:
                    print('Пауза %d секунд (%d треков)...' % (pause_sec, file_count))
                    time.sleep(pause_sec)
                    ctn = 0

                try:
                    # pprint (track)
                    config.set(album_sec, safe_fs_name(trackname), track['url'])
                    is_verbose and print(">> Добавлен %s/%s" % (atitle, trackname))
                    file_count += 1

                except configparser.DuplicateSectionError as error_msg:
                    is_verbose and print(">> Пропуск %s/%s" % (atitle, trackname))
                    continue

        except vk_api.vk_api.Captcha:
            print("Сайт требует ввести капчу, работа прекращена (обработано %d файлов)" % file_count)
            close_all(config, cfgfile, out_filename)
            return

    close_all(config, cfgfile, out_filename)
    print("Обработано %d треков" % file_count)


# ===============================================================================
def close_all(config, fh, fname):
    """ Закрыть ридер и файл """
    if fh.closed:
        fh = open(fname, 'w')
    config.write(fh)
    fh.close()


# ===============================================================================
def download(config_filename, output_path):
    """ Скачать файлы из форматированного файла """

    # Read config
    reader = configparser.ConfigParser()
    reader.read(config_filename)
    files_count = 0

    # Каждая секция качается в N потоков
    for section in reader.sections():
        dirname = "%s/%s" % (output_path, (safe_fs_name(section).title()))

        # pprint (dirname)

        # Создать директории-альбомы
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        init_threads(threads_num, dirname, dict(reader[section]))
        # time.sleep(pause_sec)

    print("Загружено %d файлов" % files_count)

# ===============================================================================
def init_threads(tnum, output_path, data_list):
    """ Запустить процессы на скачивание """

    # Create the queue and thread pool
    q = queue.Queue()
    for i in range(tnum):
        t = threading.Thread(target=down_worker, kwargs={'queue': q, 'output_path': output_path})
        t.daemon = True  # thread dies when main thread (only non-daemon thread) exits.
        t.start()

    for item in data_list.items():
        q.put(item)

    # block until all tasks are done
    q.join()


# ===============================================================================
def down_worker(queue, output_path):
    """ Скачивающий процесс """
    # title, url = queue.get()
    # fpath = '%s/%s.mp3' % (output_path, title)
    # print(fpath)
    while True:
        # pprint(queue.get())
        title, url = queue.get()
        title = title.title()  # But I couldnt stop

        try:
            fpath = '%s/%s.mp3' % (output_path, title)
            # pprint(fpath)
            if not os.path.exists(fpath):
                tmp_file = "%s.part" % fpath

                # remove tmp file
                if os.path.exists(tmp_file):
                    print("- temp file %s" % tmp_file)
                    os.remove(tmp_file)

                # add file
                print("+ %s" % title)
                urlretrieve(url, tmp_file)
                os.rename(tmp_file, fpath)
                #files_count += 1

            # skip file
            elif not is_only_downloadin:
                print("> %s" % title)

        except Exception as err:
            print(err)

        queue.task_done()


# ===============================================================================
def safe_fs_name(name):
    """ Получить имя подходящее для сохранения файлов и папок """

    name = html.unescape(name)

    newname = ''
    for c in name:
        newname += c if (c.isalnum() or c in keepcharacters) else '-'

    # black magic regex
    newname = "".join(newname).strip()
    newname = re.sub(r'\-+', '-', newname)
    newname = re.sub(r'\s?\-\s?', '-', newname)
    newname = re.sub(r'\-$', '', newname)

    return newname


# ===============================================================================
# public static void
# ===============================================================================
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("action", type=str, help="Действие: parse|download")
    parser.add_argument("config", type=str, help="Файл с параметрами входа на ВК")
    parser.add_argument("output", type=str, help="Куда сохранить результаты")
    parser.add_argument("-v", "--verbose", help="Подробные сообщения", action="store_true", default=True)
    parser.add_argument("-e", "--every", help="Пауза каждые n треков", type=int, default=200)
    parser.add_argument("-p", "--pause", help="Продолжительность паузы, секунды", type=int, default=15)
    parser.add_argument("-t", "--threads", help="Количество процессов на закачку", type=int, default=5)

    args = parser.parse_args()

    if args.action == 'download':
        is_verbose = args.verbose
        threads_num = args.threads
        pause_sec = args.pause

        download(args.config, args.output)

    elif args.action == 'parse':
        is_verbose = args.verbose
        sleep_every_tracknum = args.every
        pause_sec = args.pause

        parse(args.config, args.output)
    else:
        raise Exception('Неизвестное дейтсвие')
