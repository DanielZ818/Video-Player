"""
Generate video thumbnail that can be used by pylr player
+ parallel/multiprocessing
Store thumbnail in a database and folders
"""

import os
import math
import multiprocessing
import sqlite3
import time
from moviepy.editor import VideoFileClip
from PIL import Image
import numpy as np
from datetime import datetime
import hashlib
from tqdm import tqdm
from colorama import Fore
import pathlib


def generate_thumbnail(frame_num, thumbnail_width, thumbnail_height, interval, video_file):
    # Initialize VideoFileClip here instead of passing it as an argument
    video_clip = VideoFileClip(video_file)
    frame = video_clip.get_frame(frame_num * interval)
    frame = np.array(frame)
    frame = Image.fromarray(frame)
    frame = frame.resize((thumbnail_width, thumbnail_height))
    video_clip.close()  # Close the VideoFileClip to release resources
    return frame


def generate(video_file: str, output_dir: str, desire_interval=2):
    os.makedirs(output_dir, exist_ok=True)

    video_clip = VideoFileClip(video_file)
    total_duration = video_clip.duration

    # desire_interval = 2

    num_thumbnails = math.floor(total_duration / desire_interval)
    N = int(math.sqrt(num_thumbnails))
    num_thumbnails = N * N
    thumbnail_width = int(video_clip.size[0] / 10)
    thumbnail_height = int(video_clip.size[1] / 10)
    interval = total_duration / num_thumbnails

    thumbnail_grid = Image.new('RGB', (thumbnail_width * N, thumbnail_height * N))
    results = []

    num_threads = 12
    pool = multiprocessing.Pool(num_threads)

    progress_bar = tqdm(total=num_thumbnails, desc=("Generating Thumbnails for " + video_file), unit="frame",
                        bar_format="{l_bar}{bar:10}{r_bar}", ncols=150, ascii=True, colour="green")

    for i in range(num_thumbnails):
        result = pool.apply_async(generate_thumbnail, (i, thumbnail_width, thumbnail_height, interval, video_file))
        results.append((result, i))

    for result, i in results:
        frame = result.get()
        x_position = (i % N) * thumbnail_width
        y_position = (i // N) * thumbnail_height
        thumbnail_grid.paste(frame, (x_position, y_position))
        # print(f'Frame {i} processed.\t{datetime.now() - start}')
        progress_bar.update(1)

    progress_bar.close()

    # Save the thumbnail grid as a PNG image
    filename = video_file.split('\\')[-1] + ';@;' + str(N) + 'x' + str(N) + f';t;{int(time.time())}.png'
    saved_path = os.path.join(output_dir, filename)
    print(Fore.YELLOW + f"{saved_path} Saving...")
    thumbnail_grid.save(saved_path)
    print(Fore.GREEN + f"{saved_path} Saved...")

    bytes_data = thumbnail_grid.tobytes()

    video_clip.close()
    pool.close()
    pool.join()

    size_bytes = os.path.getsize(saved_path)
    md5 = hashlib.md5(open(saved_path, 'rb').read()).hexdigest()

    tn = Thumbnail(filename=video_file, thumbnail_name=filename, path=saved_path, size_bytes=size_bytes, md5=md5,
                   raw_data=bytes_data, tb_num=N * N, tb_row=N, tb_col=N, tb_total_x=thumbnail_width * N,
                   tb_total_y=thumbnail_height * N)

    return tn


class Thumbnail:
    def __init__(self, filename, thumbnail_name, path, size_bytes, md5, raw_data, tb_num, tb_row, tb_col, tb_total_x,
                 tb_total_y):
        self.filename = filename  # video filename
        self.thumbnail_name = thumbnail_name  # thumbnail filename
        self.path = path  # thumbnail saved path
        self.size_bytes = size_bytes  # thumbnail size in bytes
        self.md5 = md5  # thumbnail md5
        self.raw_data = raw_data  # thumbnail raw data
        self.tb_num = tb_num  # total pic in thumbnail
        self.tb_row = tb_row  # row num
        self.tb_col = tb_col  # col num
        self.tb_total_x = tb_total_x  # png total horizontal pixels
        self.tb_total_y = tb_total_y  # png total vertical pixels


# For Hierarchy structure
class Video:
    def __init__(self, filename, associated_thumbnail_path, original_path, path, size_bytes, md5):
        self.filename = filename  # video filename
        self.associated_thumbnail_path = associated_thumbnail_path  # associated thumbnail path
        self.original_path = original_path  # video original path from mega
        self.path = path  # reorganized path
        self.size_bytes = size_bytes  # video size in bytes
        self.md5 = md5  # video md5


class DB:
    def __init__(self, database_path):
        self.connection = sqlite3.connect(database_path)
        self.cursor = self.connection.cursor()

    # def insert_hierarchy_entry(self, filename, original_path, path, size_bytes, md5):
    #     insert_query = "INSERT INTO HIERARCHY (filename, thumbnail_name, path, size_bytes, md5) VALUES (?, ?, ?, ?, ?)"
    #     self.cursor.execute(insert_query, (filename, original_path, path, size_bytes, md5))
    #     self.connection.commit()

    def insert_tn(self, thumbnail: Thumbnail):
        print(Fore.YELLOW + "Inserting into db...")
        insert_query = "INSERT INTO THUMBNAIL (filename, thumbnail_name, path, size_bytes, md5, raw_data, tb_num, " \
                       "tb_row, tb_col, tb_total_x, tb_total_y) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        self.cursor.execute(insert_query, (thumbnail.filename, thumbnail.thumbnail_name, thumbnail.path,
                                           thumbnail.size_bytes, thumbnail.md5, thumbnail.raw_data, thumbnail.tb_num,
                                           thumbnail.tb_row, thumbnail.tb_col, thumbnail.tb_total_x,
                                           thumbnail.tb_total_y))
        self.connection.commit()
        print(Fore.GREEN + "Done!")

    def reset_id(self, table_name):
        query = f"UPDATE SQLITE_SEQUENCE SET SEQ=0 WHERE NAME='{table_name}'"
        self.cursor.execute(query)
        self.connection.commit()

    def close_connection(self):
        self.connection.close()


class Os_file:
    def __init__(self, filename, filepath, size):
        self.filename = filename
        self.filepath = filepath
        self.size = size


def list_files_in_directory(directory) -> [Os_file]:
    count = 0
    lst: [Os_file] = []
    not_mp4: [Os_file] = []

    total_file_num = 0
    for root_dir, cur_dir, files in os.walk(directory):
        total_file_num += len(files)

    progress_bar = tqdm(total=total_file_num, desc=("Discovering Files in " + directory), unit="files",
                        bar_format="{l_bar}{bar}{r_bar}", ncols=150, ascii=True, colour="green")
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            size = os.path.getsize(file_path)
            file_ext = pathlib.Path(file_path).suffix
            if file_ext != '.mp4' and file_ext != '.png':
                not_mp4.append(Os_file(file, file_path, size))
                continue
            if file[0] == '.':
                continue
            count += 1
            # file: filename, root[14::]: org_filepath, size: in bytes, count: count
            # print(root[26::], file, size, count)
            lst.append(Os_file(file, file_path, size))
            progress_bar.update(1)
    progress_bar.close()
    print(f"{count} files were found in {directory}.")
    for x in not_mp4:
        print(Fore.RED + x.filename, x.filepath, f'({pathlib.Path(x.filepath).suffix})', "is not not mp4")
    return lst


if __name__ == '__main__':
    database = DB('thumbnail.db')
    video_directory = ''
    # video_directory = 'vid_dir'
    # saved_thumbnail_directory = 'saved_thumbnail'
    saved_thumbnail_directory = ''
    desire_interval = 10

    # DO NOT RUN THIS COMMAND: ENTRY ALREADY EXISTS
    # database.reset_id('THUMBNAIL')

    file_lst = list_files_in_directory(video_directory)
    thumbnail_lst = list_files_in_directory(saved_thumbnail_directory)
    saved_thumbnail_name_lst = []
    for i in thumbnail_lst:
        saved_thumbnail_name_lst.append(i.filename)

    cur = 0
    start_time = datetime.now()
    errors = []
    for i in file_lst:
        cur += 1
        print(Fore.CYAN + "----------------------------------------------")
        video_name, video_path, video_size = i.filename, i.filepath, i.size

        alr_gen = False
        for name in saved_thumbnail_name_lst:
            if video_name in name:
                print(Fore.MAGENTA + f"{video_name} has already been generated!")
                alr_gen = True
                break
        if alr_gen:
            continue
        # try:
        thumbnail = generate(video_path, saved_thumbnail_directory, desire_interval=desire_interval)
        database.insert_tn(thumbnail)
        print(Fore.GREEN + video_path, "Complete!", f'{cur}/{len(file_lst)}', "\tTime Elapsed:",
              datetime.now() - start_time)
    # except Exception as e:
    #     errors.append((video_path, e))
    #    print(Fore.YELLOW + f"{video_path} Error:", Fore.RED + str(e).replace('\n', '\t'))

    database.close_connection()
    print(Fore.CYAN + '===================================================')
    print("Summary:")
    print(Fore.GREEN + "Success:", len(file_lst) - len(errors), 'out of', len(file_lst))
    print(Fore.RED + "Errors:", len(errors))
    for err in errors:
        print(Fore.YELLOW + err[0], Fore.RED + str(err[1]).replace('\n', '\t'))
    print(Fore.CYAN + '===================================================')
