import networkx
import logging
import pickle
import os
import angr
from collections import defaultdict
from .lmd import LibMatchDescriptor
from .utils import PROJECT_KWARGS
from .libmatch import LibMatch
from .utils import score_matches

l = logging.getLogger("bdsig.lmdb")
l.setLevel("DEBUG")

class LibMatchDatabase(object):
    """
    A container for a lot of LibMatchDescriptors and their metadata.

    An LMDB is based on a set of libraries in a directory structure, similar to how they are found on the filesystem.
    The top level should contain folders for each arch-tuple (e.g., arm-none-eabi-)
    THe next level should consist of one folder per library.
    Under that, they can contain any arbitrary folder structure (e.g., you can just pile a bunch of library folders in there and it'll get figured out)
    """
    def __init__(self, lib_lmds):
        self.lib_lmds = lib_lmds
        self._build_sym_list(lib_lmds)
        self.symbols = defaultdict(list) # Mapping of string names to all the libraries and objects that contain them.
                                                      # Used primarily for scoring

    def _smoosh(self, candidates):
        for f_addr, stuff in candidates.items():
            if len(stuff) <= 1:
                continue

            name = stuff[0][2].function_b.name
            for lib, lmd, fd in stuff:
                if name != fd.function_b.name:
                    break
            else:
                # Smoosh it!
                candidates[f_addr] = [stuff[0]]
        return candidates

    def _postprocess_matches(self, target_lmd, results):
        """
        Clean up the matches for the user.
        This encodes the behavior "we consider it a match if we 
        match with exactly one name"
        """
        final_matches = {}
        collisions = 0
        junk = 0
        guesses = 0
        for f_addr, match_infos in results.items():
            if len(match_infos) > 1:
                collisions += 1    
                continue
            if f_addr not in target_lmd.viable_functions:
                # we put a name on it, but it's a stub!
                # What. Ever.
                junk += 1
                continue
            for lib, lmd, match in match_infos:
                if isinstance(match, str):
                    sym_name = match
                    guesses += 1
                else:
                    obj_func_addr = match.function_b.addr
                    sym_name = lmd.function_manager.get_by_addr(obj_func_addr).name
                final_matches[f_addr] = sym_name
        l.warning("Detected %d collisions" % collisions)
        l.warning("Ignored %d junk function matches" % junk)
        l.warning("Made %d guesses", guesses)
        l.warning("Matched %d symbols" % len(list(final_matches.keys())))
        return final_matches

    def match(self, lmd_path, score=False):
        """
        Scan the database and try to match all libraries with the target.

        :param lib: Either a string (program path) or a LibMatchDescriptor
        :return: A dictionary of addresses in the program to possible symbols.
        """
        if isinstance(lmd_path, LibMatchDescriptor):
            lmd = lmd_path
        else:
            lmd = LibMatchDescriptor.load_path(lmd_path)
        candidates = []
        try:
            self.lm = LibMatch(lmd, self)
            candidates = self.lm._candidate_matches
            plain_candidates = self.lm._plain_matches
        except Exception as e:
            l.exception("Error computing matches")
            raise
        # TODO: This is where we put multi-library heuristics!

        candidates = self._smoosh(candidates)
        plain_candidates = self._smoosh(plain_candidates)
        if score:
            print("############### UNREFINED MATCHES ###############")
            score_matches(lmd_path, plain_candidates, self)
            input()
            print("############### FINAL MATCHES ###############")
            score_matches(lmd_path, candidates, self)

        out = self._postprocess_matches(lmd, candidates)
        return out

    # Creation and Serialization
    @staticmethod
    def _build_lib(lib_dir):
        lmds = set()
        for dirName, subdirList, fileList in os.walk(lib_dir):
            l.info('Found directory: %s' % dirName)
            for fname in fileList:
                if fname.endswith(".o") or fname.endswith(".obj"):
                    fullfname = os.path.join(dirName, fname)
                    l.info("Making signature for " + fullfname)
                    try:
                        lmds.add(LibMatchDescriptor.make_signature(fullfname, **PROJECT_KWARGS))
                    except angr.errors.AngrCFGError:
                        l.warning("No executable data for %s, skipping" % fullfname)
                    except Exception as e:
                        l.exception("Could not make signature for " + fullfname)
        return lmds

    @staticmethod
    def build(root_dir, dbfile=None):
        """
        Constructor to build the database, from a directory tree

        :param root_dir:
        :return: the LMDB
        """
        lmds = dict() # mapping of the lib's name, to the list of lmds it contains
        if not os.path.isdir(root_dir):
            raise ValueError("Must provide a directory to build a database!")
        # Divide each folder within the directory into libraries
        for thing in os.listdir(root_dir):
            fullname = os.path.join(root_dir, thing)
            if os.path.isdir(fullname):
                l.info("Building signatures for library %s (%s)" % (thing, fullname))
                lmds[thing] = LibMatchDatabase._build_lib(fullname)

        l.info("Making LMDB")
        lmdb = LibMatchDatabase(lmds)
        directory = os.path.dirname(os.path.abspath(root_dir))

        if dbfile == None:
            dbfile = os.path.join(directory, os.path.basename(os.path.abspath(root_dir)) + ".lmdb")
        lmdb.dump_path(dbfile)
        l.info("Done")

    def _build_sym_list(self, lmds):
        """
        Build the total list of symbols this database contains.
        If its not in this list, we are for sure not going to match well with it
        (used for scoring)
        :param lmds:
        :return:
        """
        syms = set()
        for _, lmd_list in lmds.items():
            for lmd in lmd_list:
                names = {x.name for x in lmd.viable_symbols}
                syms.update(names)
        self.symbol_names = syms

    @staticmethod
    def load_path(p):
        with open(p, "rb") as f:
            return LibMatchDatabase.load(f)

    @staticmethod
    def load(f):
        lmdb = pickle.load(f)

        if not isinstance(lmdb, LibMatchDatabase):
            raise ValueError("That's not a InterObjectCallgraph!")
        return lmdb

    @staticmethod
    def loads(data):
        lmdb = pickle.loads(data)

        if not isinstance(lmdb, LibMatchDatabase):
            raise ValueError("That's not a LibMatchDatabase!")
        return lmdb

    def dump_path(self, p):
        with open(p, "wb") as f:
            self.dump(f)

    def dump(self, f):
        return pickle.dump(self, f, pickle.HIGHEST_PROTOCOL)

    def dumps(self):
        return pickle.dumps(self, pickle.HIGHEST_PROTOCOL)
