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


class Oyabun:
    # Local vars
    keepcharacters = (' ', '.', '_', '—', '(', ')')
    is_verbose = False
    threads_num = 5
    pause_sec = 15
    sleep_every_tracknum = 200
    output_path = './'
    files_count = 0
    is_only_downloadin = True
    only_first = -1

    #==========================================================================
    def parse(self, config_filename, out_filename):
        """ Загрузка альбомов в ini-файл
            NB: Максимальное число альбомов для запроса - 100
            https://vk.com/dev/audio.getAlbums
        """

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
        albums = vk.audio.getAlbums(owner_id=_user_id, count=100)  # NB!

        if not albums:
            raise Exception('No albums loaded')

        # Подготовка файла
        config.read(out_filename)
        cfgfile = open(out_filename, 'w')
        ctn, files_count = 0, 0

        # Заполнить файл альбомами, которых ещё нет
        for album in albums['items']:
            aid, atitle = album['id'], album['title']
            album_sec = self.safe_fs_name(atitle)  # "%s | %s" % (atitle, aid)

            try:
                config.add_section(album_sec)
                self.is_verbose and print("> Добавлен %s" % atitle)

            except configparser.DuplicateSectionError as error_msg:
                self.is_verbose and print("> Пропуск %s" % atitle)

            # Заполнить альбом треками
            try:
                tracks = vk.audio.get(owner_id=_user_id, album_id=aid)

                for track in tracks['items']:
                    trackname = "%s — %s" % (track['artist'], track['title'])

                    # Пауза
                    ctn += 1
                    if self.sleep_every_tracknum < ctn:
                        print('Пауза %d секунд (%d треков)...' % (self.pause_sec, files_count))
                        time.sleep(self.pause_sec)
                        ctn = 0

                    try:
                        # pprint (track)
                        config.set(album_sec, self.safe_fs_name(trackname), track['url'])
                        self.is_verbose and print(">> Добавлен %s/%s" % (atitle, trackname))
                        files_count += 1

                        # Опция для первых N треков
                        if self.only_first and (files_count >= self.only_first):
                            raise RuntimeError
                            return

                    except configparser.DuplicateSectionError as error_msg:
                        self.is_verbose and print(">> Пропуск %s/%s" % (atitle, trackname))
                        continue

            except vk_api.vk_api.Captcha:
                print("CAPTCHA request from site, script quitted (%d files processed)" % files_count)

            except RuntimeError:
                print("Only first %d tracks processed" % files_count)
                return

            finally:
                self.close_all(config, cfgfile, out_filename)
                print("Обработано %d треков" % files_count)

    # ==========================================================================
    def close_all(self, config, fh, fname):
        """ Закрыть ридер и файл """
        if fh.closed:
            fh = open(fname, 'w')
        config.write(fh)
        fh.close()

    # ==========================================================================
    def download(self, config_filename, output_path):
        """ Скачать файлы из форматированного файла """

        # Read config
        reader = configparser.ConfigParser()
        reader.read(config_filename)
        files_count = 0

        # Каждая секция качается в N потоков
        for section in reader.sections():
            dirname = "%s/%s" % (output_path, (self.safe_fs_name(section).title()))

            # pprint (dirname)

            # Создать директории-альбомы
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            self.init_threads(self.threads_num, dirname, dict(reader[section]))
            # time.sleep(pause_sec)

        print("Загружено %d файлов" % files_count)

    # ==========================================================================
    def init_threads(self, tnum, output_path, data_list):
        """ Запустить процессы на скачивание """

        # Create the queue and thread pool
        q = queue.Queue()
        for i in range(tnum):
            t = threading.Thread(target=self.down_worker, kwargs={'queue': q, 'output_path': output_path})
            t.daemon = True  # thread dies when main thread (only non-daemon thread) exits.
            t.start()

        for item in data_list.items():
            q.put(item)

        # block until all tasks are done
        q.join()

    # ==========================================================================
    def down_worker(self, queue, output_path):
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
                    # files_count += 1

                # skip file
                elif not self.is_only_downloadin:
                    print("> %s" % title)

            except Exception as err:
                print(err)

            queue.task_done()

    # ==========================================================================
    def safe_fs_name(self, name):
        """ Получить имя, подходящее для сохранения файлов и папок """

        name = html.unescape(name)
        newname = ''

        for c in name:
            newname += c if (c.isalnum() or c in self.keepcharacters) else '-'

        # black magic regex
        newname = "".join(newname).strip()
        newname = re.sub(r'\-+', '-', newname)
        newname = re.sub(r'\s?\-\s?', '-', newname)
        newname = re.sub(r'\-$', '', newname)

        return newname

    # ==========================================================================
    def init(self):
        """ Разобрать опции и запустить команду """

        parser = argparse.ArgumentParser(description="Oyabun is VKontakte audio albums downloader")
        parser.add_argument("action", help="Action: parse|download", type=str)
        parser.add_argument("output", help="Output path of an action", type=str)
        parser.add_argument("-с", "--config", help="File with auth params (VK login and pass)", type=str,
                            default='config.ini')
        parser.add_argument("-v", "--verbose", help="Enable verbose output", action="store_true", default=self.is_verbose)
        parser.add_argument("-e", "--every", help="Pause each n tracks", type=int, default=self.sleep_every_tracknum)
        parser.add_argument("-p", "--pause", help="Pause duration in seconds", type=int, default=self.pause_sec)
        parser.add_argument("-t", "--threads", help="Threads to download number", type=int, default=self.threads_num)
        parser.add_argument("-f", "--first", help="First n tracks", type=int)
        args = parser.parse_args()

        self.is_verbose = args.verbose
        self.sleep_every_tracknum = args.every
        self.pause_sec = args.pause
        self.threads_num = args.threads
        self.only_first = args.first

        try:
            getattr(self, args.action)(args.config, args.output)
        except AttributeError:
            print('Unknown action')
            parser.print_usage()

# ==============================================================================
# public static void
# ==============================================================================
if __name__ == '__main__':
    Oyabun().init()
