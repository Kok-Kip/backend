from app.database.document import get_documents_by_ids, get_document_number, get_document_details
from app.database.word import get_word_by_term, get_frequent_words, get_words_embedding_byte
from app.database.wordDocRef import get_word_doc_ref_by_word_id
from app.biz.embedding import get_embedding, bytes2Embedding
from app.biz.common import *
from app import logger
import jieba
from typing import Dict
import math
import time


# const parameters for bm25
k1 = 2
b = 0.75
avgdl = 50  # Document Average Length


def get_pertinent_doc_by_key(query):
    seg = jieba.cut_for_search(query)
    score = get_score_of_document(seg)
    doc_ids = get_best_document_by_score(score, 10)
    details = get_document_details(doc_ids)
    return details


def get_best_document_by_score(score, k: int):
    items = score.items()
    reverse_score = [[v[1], v[0]] for v in items]
    reverse_score.sort(reverse=True)
    sorted_score = reverse_score[:k]
    document_ids = [s[1] for s in sorted_score]
    return document_ids


def get_score_of_document(seg) -> Dict[int, float]:
    # score = w1 * tfidf + w2 * bm25 + w3 * word-embedding
    w1 = 0.3
    w2 = 0.3
    w3 = 0.4

    seg1 = list(seg)
    if len(seg1) == 0:
        return dict()

    # calculate tiidf
    start_time = time.time()
    tfidf = get_score(seg1, True)
    logger.info(f'tfidt score: {tfidf}')
    logger.info(f'tfidt algorithm spent {time.time() - start_time}s')

    # calculate bm25
    start_time = time.time()
    bm25 = get_score(seg1, False)
    logger.info(f'bm25 score: {bm25}')
    logger.info(f'bm25 algorithm spent {time.time() - start_time}s')

    # calculate embedding
    start_time = time.time()
    emb = get_score_embedding(seg1)
    logger.info(f'embedding score: {emb}')
    logger.info(f'embedding algorithm spent {time.time() - start_time}s')

    add_dict(tfidf, bm25)
    add_dict(emb, bm25)
    logger.info(f'total score: {bm25}')
    return bm25


def get_score(seg, score_type=True) -> Dict[int, float]:
    # score_type 为真时用 tfidf 算法, 为假时用 bm25 算法
    score = dict()
    for term in seg:
        score_temp = calculate_score(term, score_type)
        add_dict(score_temp, score)
    normalize_score(score)
    return score


def calculate_score(term, score_type=True) -> Dict[int, float]:
    score = dict()

    # 1. find all relevant documents
    word = get_word_by_term(term)
    if word is None:
        return score
    word_id = word.id

    N = get_document_number()

    word_doc_refs = get_word_doc_ref_by_word_id(word_id)
    n = len(word_doc_refs)
    idf = math.log(N / n)

    document_ids = [r.document_id for r in word_doc_refs]
    documents = get_documents_by_ids(document_ids)

    for ref in word_doc_refs:
        if score_type:
            # score_type 为真时用 tfidf 算法
            score[ref.document_id] = (ref.frequency / documents[ref.document_id].length) * idf
        else:
            # score_type 为假时用 em25 算法
            K = k1 * (1 - b + b * documents[ref.document_id].length / avgdl)
            score[ref.document_id] = (ref.frequency * (k1 + 1) / (ref.frequency + K)) * idf
    return score

  
def get_score_embedding(seg):
    score = {}
    all_high_frequency_word_list = get_frequent_words(3)
    # for each document, calculate similarity
    for document_id, word_list in all_high_frequency_word_list.items():
        count = 0
        emb_list = get_words_embedding_byte(word_list)
        document_score = 0
        for s in seg:
            s_emb = get_embedding(s)
            if s_emb is None:
                continue
            for emb in emb_list.values():
                emb = bytes2Embedding(emb)
                count += 1
                cos = calculate_cosine_similarity(s_emb, emb)
                document_score += cos
        if count == 0:
            continue
        document_score /= count
        score[document_id] = document_score
    normalize_score(score)
    return score


def normalize_score(score):
    length = len(score)
    if length == 0:
        return dict()
    mean = 0
    for value in score.values():
        mean += value
    mean = mean / length

    variance = 0
    for value in score.values():
        variance += math.pow(value - mean, 2)

    variance = math.sqrt(variance / length)

    for k in score.keys():
        score[k] = (score[k] - mean) / variance
