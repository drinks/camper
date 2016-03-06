import os
import pickle
from tagger import tagger as tgr

datafile = os.path.join(os.path.dirname(__file__), '..', 'data/dict.pkl')
# print datafile
weights = pickle.load(open(datafile, 'rb'))
rdr = tgr.Reader()
stmr = tgr.Stemmer()
rtr = tgr.Rater(weights)

extract_tags = tgr.Tagger(rdr, stmr, rtr)
