#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import base64
import configparser
import os
import re
import sys
import time
import vk_api
import threading
import queue
from urllib.request import urlretrieve


class Oyabun:
    """
        Загрузчик аудио-альбомов из Vkontakte.

        :author Okto <web@axisful.info>
        :link http://blog.axisful.info/code/python/VkSoundOyabun
    """

    keepcharacters = (" ", ".", "_", "—", "(", ")")
    output_path = os.path.curdir
    path_delimeter = "-"

    is_verbose = False
    is_only_downloadin = False
    only_first = None

    threads_num = 5
    pause_sec = 15
    sleep_each_tracknum = 200
    albums_count = 100
    files_count = 0

    # ==========================================================================
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
        reader.read(config_filename, encoding="utf-8")

        try:
            _user_id = reader.get("USER", "id")
            _pass = reader.get("USER", "pass")
            _login = reader.get("USER", "login")
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
            raise RuntimeError("No albums loaded")

        # Подготовка файла
        albums_config = configparser.ConfigParser()
        albums_config.read(out_filename, encoding="utf-8")
        albums_fh = open(out_filename, "w", encoding="utf-8")
        ctn, files_count = 0, 0

        # Быстрый вызов метода
        def write_close():
            self.write_and_close(albums_config, albums_fh, out_filename)

        # Заполнить файл альбомами, которых ещё нет
        for album in albums["items"]:
            aid, atitle = album["id"], album["title"]
            album_section = self.safe_fs_name(atitle)

            try:
                albums_config.add_section(album_section)
                self.is_verbose and print("> Add album %s" % atitle)

            except configparser.DuplicateSectionError:
                self.is_verbose and print("> Skip album %s" % atitle)

            # Заполнить альбом треками
            try:
                tracks = vk.audio.get(owner_id=_user_id, album_id=aid)

                for track in tracks["items"]:
                    trackname = "%s — %s" % (track["artist"], track["title"])

                    # Пауза
                    ctn += 1
                    if self.sleep_each_tracknum < ctn:
                        print("Pause %d secs (%d tracks)..." % (self.pause_sec, self.files_count))
                        time.sleep(self.pause_sec)
                        ctn = 0

                    try:
                        # pprint (track)
                        albums_config.set(album_section, self.safe_fs_name(trackname), track["url"])
                        self.is_verbose and print(">> Add %s/%s" % (atitle, trackname))
                        self.files_count += 1

                        # Опция для первых N треков
                        if self.only_first and (self.files_count >= self.only_first):
                            raise RuntimeError

                    except configparser.DuplicateSectionError:
                        self.is_verbose and print(">> Skip %s/%s" % (atitle, trackname))
                        continue

            except vk_api.vk_api.Captcha:
                print("CAPTCHA request from site, script quitted (%d files processed)" % self.files_count)
                write_close()
                return

            except RuntimeError:
                print("Only first %d tracks processed" % self.files_count)
                write_close()
                return

        print("%d tracks processed" % self.files_count)

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
        vk_session = vk_api.VkApi(login, base64.b64decode(bytes(password, "utf-8")))
        vk_session.authorization()

        return vk_session

    @staticmethod
    def write_and_close(config, fh, fname):
        """
            Записать конфиг в файл и закрыть его
            :param config: configparser.ConfigParser
            :param fh:     TextIOWrapper
            :param fname:  str: Имя файла
        """

        if fh.closed:
            fh = open(fname, "w", encoding="utf-8")
        config.write(fh)
        fh.close()

    def download(self, config_filename, output_path):
        """
            Скачать файлы из форматированного файла в несколько потоков

            :param config_filename: str
            :param output_path:     str
            :except:                RuntimeError
        """

        # Прочитать конфиг с альбомами
        reader = configparser.ConfigParser()
        reader.read(config_filename, encoding="utf-8")

        # Каждая секция качается в threads_num потоков
        for section in reader.sections():
            albumname = self.safe_fs_name(section).title()
            dirname = os.path.join(output_path, albumname)

            # Создать директории-альбомы
            if not os.path.exists(dirname):
                os.makedirs(dirname)

            self.is_verbose and print("[%s]" % albumname)
            self.init_threads(dirname, dict(reader[section]))

        print("%d files donwloaded" % self.files_count)

    def init_threads(self, output_path, tracks_list):
        """
            Запустить потоки на скачивание

            :param output_path: str
            :param tracks_list: dict
        """

        # Создать очередь и пул потоков
        tracks_queue = queue.Queue()

        for item in tracks_list.items():
            tracks_queue.put(item)

        for i in range(self.threads_num):
            t = threading.Thread(target=self.down_worker,
                                 kwargs={"tracks_queue": tracks_queue, "output_path": output_path})
            t.daemon = True  # thread dies when main thread (only non-daemon thread) exits.
            t.start()

        # block until all tasks are done
        tracks_queue.join()

    def down_worker(self, tracks_queue, output_path):
        """
            Скачивающий поток

            :param tracks_queue: queue.Queue
            :param output_path: str
        """

        while True:
            title, url = tracks_queue.get()
            title = title.title()  # I just couldn't stop

            try:
                fpath = os.path.join(output_path, "%s.mp3" % title)

                if not os.path.exists(fpath):
                    tmp_file = "%s.part" % fpath

                    # remove tmp file
                    if os.path.exists(tmp_file):
                        self.is_verbose and print("- temp file %s" % tmp_file)
                        os.remove(tmp_file)

                    # add file
                    self.is_verbose and print("↓ %s" % title)
                    urlretrieve(url, tmp_file)
                    os.rename(tmp_file, fpath)
                    self.files_count += 1

                # skip file
                elif not self.is_only_downloadin:
                    self.is_verbose and print("> %s" % title)

            except Exception as err:
                self.is_verbose and print(err)

            tracks_queue.task_done()

    def safe_fs_name(self, name):
        """
            Получить имя, подходящее для сохранения файлов и папок

            :param name: str
            :return str
        """

        newname = ""

        # Оставить в имени только буквы, цифры и разрешённые символы,
        # заменяя всё остальное на разделитель
        for c in name:
            newname += c if (c.isalnum() or c in self.keepcharacters) else self.path_delimeter

        # black magic regex (only for default delimeter)
        newname = "".join(newname)
        newname = re.sub(r"-{2,}", "-", newname)
        newname = re.sub(r"(\s-)|(-\s)", " - ", newname)
        newname = re.sub(r"\s-\s", " — ", newname)
        newname = re.sub(r"—-", "—", newname)
        newname = re.sub(r"— —", "—", newname)
        newname = re.sub(r"[-—]?$", "", newname)
        newname = re.sub(r"\s{2,}", " ", newname)
        newname = newname.strip()

        return newname

    def init(self):
        """ Разобрать опции и запустить команду """

        # export DEBUG_OYABUN=true
        if os.environ.get("DEBUG_OYABUN"):
            from pprint import pprint
            pprint("Started in debug mode")

        parser = argparse.ArgumentParser(description="Oyabun is VKontakte audio albums downloader")
        parser.add_argument("action", help="Action: parse|download", type=str)
        parser.add_argument("config", help="File with auth params (VK login and pass)")
        parser.add_argument("target", help="Target path of an action (directory or config file)", type=str)
        parser.add_argument("-v", "--verbose", help="Enable verbose output",
                            action="store_true", default=self.is_verbose)
        parser.add_argument("-e", "--each", help="Pause each n tracks", type=int, default=self.sleep_each_tracknum)
        parser.add_argument("-p", "--pause", help="Pause duration in seconds", type=int, default=self.pause_sec)
        parser.add_argument("-t", "--threads", help="Threads to download number", type=int, default=self.threads_num)
        parser.add_argument("-f", "--first", help="First n tracks", type=int)
        parser.add_argument("-d", "--only-downloading",
                            help="Display messages only about downloading files (not skipped)",
                            action="store_true", dest="is_only_downloadin", default=False)
        args = parser.parse_args()

        self.is_verbose = args.verbose
        self.sleep_each_tracknum = args.each
        self.pause_sec = args.pause
        self.threads_num = args.threads
        self.only_first = args.first
        self.is_only_downloadin = args.is_only_downloadin

        # Динамический вызов метода action
        try:
            getattr(self, args.action)(args.config, args.target)
        except AttributeError as msg:
            print("Unknown action: %s" % msg)
            parser.print_usage()


# ==============================================================================
# public static void
# ==============================================================================
if __name__ == "__main__":
    obj = Oyabun()

    try:
        obj.init()
    except KeyboardInterrupt:
        print("\n>> Quit (%d files processed)" % obj.files_count)
