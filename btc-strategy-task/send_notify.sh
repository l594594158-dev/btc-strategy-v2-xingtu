#!/bin/bash
MESSAGE="$1"
timeout 8 openclaw message send --channel wecom --target LiuGang --message "$MESSAGE" 2>/dev/null
