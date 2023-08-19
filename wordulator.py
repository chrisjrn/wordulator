#!/usr/bin/python3

import math
import random
import statistics
import sys
import time
from enum import Enum
from collections import defaultdict
from concurrent import futures


class Classification(Enum):
    BLANK = 0
    YELLOW = 1
    GREEN = 2


class Mode(Enum):
    NO_POOL = 0
    POOL = 1
    CHUNKED_POOL = 2


HARD_MODE = True
FILTER_PLURALS = False
FIRST_GUESS = None #"tares"
TARGET_WORD = "snake"
MODE = Mode.POOL
MAX_WORKERS = 8
POOL = futures.ProcessPoolExecutor(max_workers=MAX_WORKERS)


def main():
    words = read_word_list(FILTER_PLURALS)
    play_wordle(words, FIRST_GUESS, TARGET_WORD, HARD_MODE, mode=MODE)
    #solve_every_wordle(words, FIRST_GUESS, HARD_MODE)


def solve_every_wordle(words, first_guess, hard_mode):
    f = open("answer_list.txt")
    answers = [j.split()[5].lower() for i in f if (j := i.strip())]

    scores = defaultdict(int)
    games = {
        POOL.submit(safe_play_wordle, words, first_guess, target, hard_mode, mode=Mode.NO_POOL, show_output=False): target 
        for target in answers
    }
    for i, game in enumerate(futures.as_completed(games)):
        if i % 100 == 0: 
            print(f"{i}/{len(games)}: {scores}")
        score = game.result()

        if len(score) >= 2 and score[-1] == score[-2]:
            score = score[:-1]
        
        if len(score) == 0:
            scores["BUG"] += 1
        elif len(score) > 6:
            scores["FAIL"] += 1
            print(f"{games[game]}: {score}")
        else:
            scores[len(score)] += 1
    print(scores)


def safe_play_wordle(words, first_guess, target_word, hard_mode, mode=Mode.POOL, show_output=True):
    try:
        return play_wordle(words, first_guess, target_word, hard_mode, mode=mode, show_output=show_output)
    except Exception as e:
        print("exc", e, file=sys.stderr)
        return []


def play_wordle(words, first_guess, target_word, hard_mode, mode=Mode.POOL, show_output=True):

    if first_guess != None:
        classify_first = classify_guess(first_guess, target_word)
        potential_answers = filter_words(words, first_guess, classify_first)
        guess_list = [first_guess]
    else:
        potential_answers = words
        guess_list = []
    
    if hard_mode:
        guesses = potential_answers
    else:
        guesses = words

    while len(potential_answers) > 1:
        before = time.time()

        if mode == Mode.NO_POOL:
            guess = make_guess(potential_answers, guesses)
        elif mode == Mode.POOL:
            guess = make_guess_with_pool(potential_answers, guesses, POOL)
        elif mode == Mode.CHUNKED_POOL:
            guess = make_guess_with_pool_chunked(potential_answers, guesses, POOL)

        classified = classify_guess(guess, target_word)
        potential_answers = filter_words(potential_answers, guess, classified)
        
        elapsed = time.time() - before
        if show_output:
            print(f"{guess=} {len(potential_answers)=} {elapsed=:.5f}") 

        if hard_mode:
            guesses = [i for i in potential_answers if i != guess and i not in guess_list]
        else:
            guesses = [i for i in guesses if i != guess]

        if len(guess_list) > 20:
            raise Exception(f"{target_word=} {guess_list}")
        
        guess_list.append(guess)

    if show_output:
        print(potential_answers[0])

    guess_list.append(potential_answers[0])
    
    return guess_list


def make_guess(potential_answers, all_words):
    def _score(word):
        return score_guess(word, potential_answers)

    return min(all_words, key=_score)


def make_guess_with_loop(potential_answers, possible_guesses, return_score=False):
    min_score = len(possible_guesses)
    guess = None
    for word in possible_guesses:
        score = score_guess(word, potential_answers)
        if score < min_score:
            min_score = score
            guess = word
    if not return_score:
        return guess
    else:
        return (score, guess)


def make_guess_with_pool(potential_answers, all_words, pool):
    if pool:
        all_futures = {pool.submit(score_guess, word, potential_answers): word for word in all_words}
        gen = ((future.result(), all_futures[future]) for future in futures.as_completed(all_futures))
    else:
        gen = ((score_guess(word, potential_answers), word) for word in all_words)

    score, word = min(gen)
    
    return word


def make_guess_with_pool_chunked(potential_answers, all_words, pool: futures.Executor):
    n = int(math.ceil(len(all_words) / MAX_WORKERS))
    splits = [all_words[(i * n):((i+1) * n)] for i in range(MAX_WORKERS)]

    all_futures = {pool.submit(make_guess_with_loop, potential_answers, guesses, return_score=True) for guesses in splits if guesses}
    split_results = [future.result() for future in futures.as_completed(all_futures)]
    #print(split_results[:10])

    score, word = min(split_results)
    
    return word


def score_guess(guess, words):
    counts = defaultdict(int)
    for potential_answer in words:
        classification = classify_guess(guess, potential_answer)
        counts[classification] += 1
    return statistics.mean(counts.values())


def classify_guess(guess, potential_answer):
    out = []
    for pos, letter in enumerate(guess):
        if potential_answer[pos] == letter:
            out.append(Classification.GREEN)
        elif letter in potential_answer:
            out.append(Classification.YELLOW)
        else:
            out.append(Classification.BLANK)
    return tuple(out)


def filter_words(words, guess, classification):
    output = []
    for word in words:
        for pos, (letter_class, letter) in enumerate(zip(classification, guess)):
            if letter_class == Classification.BLANK and letter in word:
                break
            elif letter_class == Classification.GREEN and word[pos] != letter:
                break
            elif letter_class == Classification.YELLOW and (word[pos] == letter or letter not in word):
                break
        else:
            output.append(word)
    return output


def read_word_list(filter_plurals=False):
    f = open("word.list")
    all_words = [line.strip() for line in f]
    words = [stripped for line in all_words if len(stripped := line.strip()) == 5]
    
    if filter_plurals:
        singulars = {word for word in all_words if len(word) in (3, 4)}
        words = [
            word for word in words if not 
            (
                (word.endswith("s") and word[:-1] in singulars) 
                or (word.endswith("es") and word[:-2] in singulars)
            )
        ]

    return words


if __name__ == "__main__":
    main()
