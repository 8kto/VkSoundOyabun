#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import vk_api
import configparser
from pprint import pprint
import re
import time
import sys

# Read config
reader = config = configparser.ConfigParser()
reader.read('config.ini')

_user_id=reader.get('USER', 'id')
_user_pass=reader.get('USER', 'pass')
_user_login=reader.get('USER', 'login')

_ini_file="./albums.ini"
keepcharacters = (' ','.','_')
isVerbose = True
sleep_every_tracknum = 800

# Main process
def main():
    """ Загрузка альбомов в ini-файл """

    vk_session = vk_api.VkApi(_user_login, _user_pass)
    config = configparser.ConfigParser()

    # Соединение с vk api
    try:
        vk_session.authorization()
    except vk_api.AuthorizationError as error_msg:
        print(error_msg)
        return

    vk = vk_session.get_api()
    albums = vk.audio.getAlbums(owner_id=_user_id, count=2)

    if (not albums):
        raise Exception('No albums loaded')

    # Хранилище id => альбом
    keys = [i['id'] for i in albums['items']]
    albums_indexed = dict(zip(keys, albums['items']))

    # Подготовка файла
    config.read(_ini_file)
    cfgfile = open(_ini_file, 'w')
    ctn, file_count = 0, 0

    tracks = vk.audio.get(owner_id=_user_id)
    for track in tracks['items']:
        trackname = "%s — %s" % (track['artist'], track['title'])
        pprint (track)

        sys.exit()
        ctn += 1
        if (sleep_every_tracknum < ctn):
            print('Пауза...')
            time.sleep(3)
            ctn = 0

        try:
            #pprint (track)
            config.set(album_sec, trackname, track['url'])
            isVerbose and print(">> Добавлен %s/%s" % (atitle, trackname))
            file_count += 1

        except configparser.DuplicateSectionError as error_msg:
            isVerbose and print(">> Пропуск %s/%s" % (atitle, trackname))
            continue


    # Заполнить файл альбомами, которых ещё нет
    for album in albums['items']:
        aid, atitle = album['id'], album['title']
        album_sec = atitle #"%s | %s" % (atitle, aid)

        try:
            config.add_section(album_sec)
            isVerbose and print("> Добавлен %s" % atitle)

        except configparser.DuplicateSectionError as error_msg:
            isVerbose and print("> Пропуск %s" % atitle)

        # Заполнить альбом треками
        try:
            tracks = vk.audio.get(owner_id=_user_id, album_id=aid)

        except vk_api.vk_api.Captcha:
            print("Сайт требует ввести капчу, работа прекращена (обработано %d файлов)" % file_count)

            if cfgfile.closed:
                cfgfile = open(_ini_file, 'w')
            config.write(cfgfile)
            cfgfile.close()



    if cfgfile.closed:
        cfgfile = open(_ini_file, 'w')
    config.write(cfgfile)
    cfgfile.close()

# public static void
if __name__ == '__main__':
    main()

#print("".join(c for c in album['atitle'] if c.isalnum() or c in keepcharacters).rstrip())

