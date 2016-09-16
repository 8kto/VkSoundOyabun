#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import vk_api
import configparser
import re
import time
import sys
import argparse
from pprint import pprint

# Local vars
keepcharacters = (' ','.','_')

# Main process
def main(config_path, output_path, is_verbose=True, sleep_every_tracknum=200, pause_sec=15):
    """ Загрузка альбомов в ini-файл """

    # Read config
    reader = config = configparser.ConfigParser()
    reader.read(config_path)

    _user_id=reader.get('USER', 'id')
    _user_pass=reader.get('USER', 'pass')
    _user_login=reader.get('USER', 'login')

    vk_session = vk_api.VkApi(_user_login, _user_pass)
    config = configparser.ConfigParser()

    # Соединение с vk api
    try:
        vk_session.authorization()
    except vk_api.AuthorizationError as error_msg:
        print(error_msg)
        return

    vk = vk_session.get_api()
    #albums = vk.audio.getAlbums(owner_id=_user_id, count=2)
    albums = vk.audio.getAlbums(owner_id=_user_id)

    if (not albums):
        raise Exception('No albums loaded')

    # Подготовка файла
    config.read(output_path)
    cfgfile = open(output_path, 'w')
    ctn, file_count = 0, 0

    # Заполнить файл альбомами, которых ещё нет
    for album in albums['items']:
        aid, atitle = album['id'], album['title']
        album_sec = atitle #"%s | %s" % (atitle, aid)

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
                if (sleep_every_tracknum < ctn):
                    print('Пауза %d секунд...' % pause_sec)
                    time.sleep(pause_sec)
                    ctn = 0

                try:
                    #pprint (track)
                    config.set(album_sec, trackname, track['url'])
                    is_verbose and print(">> Добавлен %s/%s" % (atitle, trackname))
                    file_count += 1

                except configparser.DuplicateSectionError as error_msg:
                    is_verbose and print(">> Пропуск %s/%s" % (atitle, trackname))
                    continue

        except vk_api.vk_api.Captcha:
            print("Сайт требует ввести капчу, работа прекращена (обработано %d файлов)" % file_count)
            close_all(config, cfgfile, output_path)
            return

    close_all(config, cfgfile, output_path)
    print("Обработано %d файлов" % file_count)

    #if cfgfile.closed:
        #cfgfile = open(output_path, 'w')
    #config.write(cfgfile)
    #cfgfile.close()

def close_all(config, fh, fname):
    """ Закрыть ридер и файл """
    if fh.closed:
        fh = open(output_path, 'w')
    config.write(fh)
    fh.close()

# public static void
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=str, help="Файл с параметрами входа на ВК")
    parser.add_argument("output", type=str, help="Куда сохранить результаты")
    parser.add_argument("-v", "--verbose", help="Подробные сообщения", action="store_true", default=True)
    parser.add_argument("-e", "--every", help="Пауза каждые n треков", type=int, default=200)
    parser.add_argument("-p", "--pause", help="Продолжительность паузы", type=int, default=15)

    args = parser.parse_args()
    main(args.config, args.output, args.verbose, args.every, args.pause)

#print("".join(c for c in album['atitle'] if c.isalnum() or c in keepcharacters).rstrip())

