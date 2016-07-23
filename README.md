# Clue, SAT, knowledge games

This is a little experiment with knowledge games like
[Clue](https://en.wikipedia.org/wiki/Cluedo). It started life as a "clue
assistant" to help me beat my friends and neighbors at the game, but evolved
into a platform for learning more about the game itself. It may or may not still
be usable as a clue assistant, although it certainly isn't hard to use the ideas
herein to make a mighty fine one.

See the post at http://seanbowman.me/blog/clue-sat-logic for more information.

## Install, Build, Run

The only dependency other than Python 2.7 ish is
[CryptoMiniSat](https://github.com/msoos/cryptominisat). Install that and it
should just work. The file `clue.py` contains a main function that has the
computer play itself with a small variety of settings (number of players, number
of games, etc.)

## What did humanity learn?

Probably not much, but `smartplay.txt` contains a game in which a player wins by
observing that another player passes (instead of making an accusation) at the
end of their turn. That was a smart play! This scenario answers a question of
van Ditmarsch in "The description of game actions in Cluedo." Answering
variations on that question was one impetus for writing the program you're
looking at.
