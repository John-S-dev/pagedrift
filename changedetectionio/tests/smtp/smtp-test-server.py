#!/usr/bin/env python3
import threading
import time
from aiosmtpd.controller import Controller
from flask import Flask, Response
from email import message_from_bytes
from email.policy import default

# Accept a SMTP message and offer a way to retrieve the last message via HTTP

