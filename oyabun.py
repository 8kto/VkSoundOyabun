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
    """ Загрузчик альбомов из Vkontakte """

    keepcharacters = (' ', '.', '_', '—', '(', ')')
    output_path = './'

    is_verbose = False
    is_only_downloadin = True
    only_first = None

    threads_num = 5
    pause_sec = 15
    sleep_every_tracknum = 200
    albums_count = 100
    files_count = 0

    #==========================================================================
    def parse(self, config_filename, out_filename):
        """
            Загрузка альбомов из VK в ini-файл
            NB: Максимальное число альбомов для запроса - 100 (albums_count)
            https://vk.com/dev/audio.getAlbums

            :param config_filename: str
            :param out_filename:    str
            :except:                RuntimeError
        """

        # Прочитать файл с настройками vk-логина
        reader = configparser.ConfigParser()
        reader.read(config_filename)

        try:
            _user_id = reader.get('USER', 'id')
            _pass = reader.get('USER', 'pass')
            _login = reader.get('USER', 'login')
        except (configparser.NoSectionError, configparser.NoOptionError) as error_msg:
            self.is_verbose and print(error_msg)
            sys.exit("Wrong config")

        # Соединение с vk api
        try:
            vk_session = self.get_vk_session(_login, _pass)
        except vk_api.AuthorizationError as error_msg:
            self.is_verbose and print(error_msg)
            sys.exit(error_msg)

        vk = vk_session.get_api()
        albums = vk.audio.getAlbums(owner_id=_user_id, count=self.albums_count)  # NB!

        if not albums:
            raise RuntimeError('No albums loaded')

        # Подготовка файла
        albums_config = configparser.ConfigParser()
        albums_config.read(out_filename)
        albums_fh = open(out_filename, 'w')
        ctn, files_count = 0, 0

        write_close = lambda: self.write_and_close(albums_config, albums_fh, out_filename)

        # Заполнить файл альбомами, которых ещё нет
        for album in albums['items']:
            aid, atitle = album['id'], album['title']
            album_section = self.safe_fs_name(atitle)

            try:
                albums_config.add_section(album_section)
                self.is_verbose and print("> Add album %s" % atitle)

            except configparser.DuplicateSectionError:
                self.is_verbose and print("> Skip album %s" % atitle)

            # Заполнить альбом треками
            try:
                tracks = vk.audio.get(owner_id=_user_id, album_id=aid)

                for track in tracks['items']:
                    trackname = "%s — %s" % (track['artist'], track['title'])

                    # Пауза
                    ctn += 1
                    if self.sleep_every_tracknum < ctn:
                        print('Pause %d secs (%d tracks)...' % (self.pause_sec, files_count))
                        time.sleep(self.pause_sec)
                        ctn = 0

                    try:
                        # pprint (track)
                        albums_config.set(album_section, self.safe_fs_name(trackname), track['url'])
                        self.is_verbose and print(">> Add %s/%s" % (atitle, trackname))
                        files_count += 1

                        # Опция для первых N треков
                        if self.only_first and (files_count >= self.only_first):
                            raise RuntimeError
                            return

                    except configparser.DuplicateSectionError:
                        self.is_verbose and print(">> Skip %s/%s" % (atitle, trackname))
                        continue

            except vk_api.vk_api.Captcha:
                print("CAPTCHA request from site, script quitted (%d files processed)" % files_count)
                write_close()

            except RuntimeError:
                print("Only first %d tracks processed" % files_count)
                write_close()
                return

        print("%d tracks processed" % files_count)

    # ==========================================================================
    @staticmethod
    def get_vk_session(login, password):
        """
            Прочитать параметры соединения и вернуть vk-сессию

            :param password: str
            :param login: str
            :return: vk_api.VkApi
            :except vk_api.AuthorizationError
        """

        # Соединение с vk api
        vk_session = vk_api.VkApi(login, password)
        vk_session.authorization()

        return vk_session

    # ==========================================================================
    @staticmethod
    def write_and_close(config, fh, fname):
        """
            Записать конфиг в файл и закрыть его
            :param config: configparser.ConfigParser
            :param fh:     TextIOWrapper
            :param fname:  str: Имя файла
        """

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

        # Динамический вызов метода action
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
