# Sources & References

Links and resources referenced during the security review and hardening of this tool.

## Tool & Library References

- [ShazamIO](https://github.com/shazamio/ShazamIO) - Async Python library for Shazam API (reverse-engineered)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube/audio download library
- [pydub](https://github.com/jiaaro/pydub) - Audio manipulation library

## Similar Projects

- [setlist-maker](https://github.com/brigleb/setlist-maker) - DJ set tracklist generator using Shazam
- [Shazam-Tool (upstream)](https://github.com/in0vik/Shazam-Tool) - Original repository this fork is based on
- [stream-music-recognition](https://github.com/Uniquenik/stream-music-recognition) - Shazam-based stream recognition
- [SongRec](https://github.com/marin-m/SongRec) - Open-source Shazam client in Rust
- [shazam-cli](https://github.com/loiccoyle/shazam-cli) - CLI music recognition tool

## Security Review References

- [OWASP Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) - Path traversal attack patterns
- [OWASP Input Validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) - Input validation best practices
- [Python tempfile docs](https://docs.python.org/3/library/tempfile.html) - Secure temporary file handling
- [yt-dlp output template](https://github.com/yt-dlp/yt-dlp#output-template) - yt-dlp filename sanitization options
- [CWE-22: Path Traversal](https://cwe.mitre.org/data/definitions/22.html) - CWE classification for path traversal
- [CWE-918: SSRF](https://cwe.mitre.org/data/definitions/918.html) - Server-Side Request Forgery classification
