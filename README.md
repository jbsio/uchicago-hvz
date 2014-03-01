# University of Chicago Humans versus Zombies

**THIS DOCUMENTATION PAGE IS CURRENTLY UNDER DEVELOPMENT.**


## Description

This is the official repository for the University of Chicago (UChicago) Humans versus Zombies website and game engine.
While this game engine was developed with features specific to our campus and game in mind, you will likely find our
implementation useful. The reference implementation is available at https://www.uchicagohvz.org. 

This codebase is made available under the terms of the MIT license.

## Features

* Create and run multiple games, simultaneously if desired
* Pre-register players, and record players' majors and dorms
* Real-time stats - game analytics, individual and squad leaderboards
* Google Maps-powered kill geotagging support, with ability to define rectangular game boundaries
* Add notes to kills
* Ability for players to go back and edit kill geotags/notes later
* Squad support
* Separate radio-like chat rooms for humans and zombies (no history and no usernames shown, only timestamps)
* "Award" system for assigning/deducting points to players (useful for missions, minigames, etc.)
* High-value Target and High-value Dorm system, which awards additional points for killing a specific
player or players from a specific dorm within a specified timeframe
* Individual profile pages for players, squads, and kills
* Kill logging via web and Nexmo SMS
* Track gun rentals and returns
* Full-featured admin panel

## Requirements

* Django 1.6.x
* Django-supported database backend (PostgreSQL recommended)
* Celery 3.1.x + supported task queue (Redis recommended)
