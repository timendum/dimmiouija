# DimmiOuija bot

## Description
DimmiOuija bot is a reddit bot that manages /r/DimmiOuija subreddit

## Requirements
- A python 3.5 or higher capable machine
- ```praw```
- ```grapheme```, to handle unicode chars
- ```Jinja2```, to create summary pages (optional)

## How to install ?
1. Clone this repo in your web folder (ex: /var/www).
2. ```pip install -r requirements.txt```
3. run it via ```python bot.py```

## Wiki pages

The bot is also capable of creating summary pages on subreddit wiki.

1. run ```python dump.py``` to create a JSON snapshot
1. run ```python summary.py``` to create the new page and update index

## License

Copyright (c) 2020 Timendum

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
