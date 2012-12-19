#!/usr/bin/env python3
"""
Overview:
This script takes a bulk_extractor feature file and assembles gestalt
features out of discovered components. The motivating case was in
development of HTTP header extraction, where header field-value
pairs could be found in any order and in some cases multiple times.

The basic algorithm is to index the features by their forensic
paths, and gradually join them as overlapping feature components'
contexts are found.

For usage, run without arguments.
"""

__version__ = "0.5.3"

import sys
import copy
import bisect
import argparse
import collections
import re
import ast
import curses.ascii

#Could stand to bring in defualtdict instead of all this 2-3 line dict-of-lists priming business.
# https://gist.github.com/2012250

def dprint(s):
    sys.stderr.write(repr(s))
    sys.stderr.write("\n")

def unescape_be_bytestring(bs):
    """
    Bulk Extractor 1.2.2 encodes non-ASCII bytes with octal escaping.  This was surprisingly non-obvious to unescape into a byte array with built-in Python functions.
        Iterated encodings may output with backslash-x escaping.
        ast.literal_eval seems to be the best offering.
    Input: byte string with octal or hex encoding
    Returns: byte string with backslash-0 and backslash-x sequences escaped (bonus: ast.literal_eval catches others too)
    """
    
    if type(bs) != type(b''):
        raise ValueError("unescape_be_string: Expected input type to be %r." % type(b''))
    #Encode non-ASCII bytes once. Unicode decoding pukes on bytes in [128,255].
    ascii_bytes_list = []
    for b in bs:
        if curses.ascii.isprint(chr(b)):
            ascii_bytes_list.append(chr(b).encode())
        else:
            ascii_bytes_list.append(b"\\" + hex(b)[1:].encode())
    ascii_bytes = b"".join(ascii_bytes_list)
    #A little looping is required for handling literal single-quotes
    escquoted_parts = ascii_bytes.split(b"\\'")
    decoded_escquoted_parts = []
    for escquoted_part in escquoted_parts:
        quoted_parts = escquoted_part.split(b"'")
        try:
            decoded_escquoted_part = b"'".join([ast.literal_eval("b'" + bpart.decode() + "'") for bpart in quoted_parts])
        except Exception:
            dprint("Error from %r." % quoted_parts)
            raise
        decoded_escquoted_parts.append(decoded_escquoted_part)
        retval = b"\\'".join(decoded_escquoted_parts)
    return retval

def bytes_to_string(bs):
    """
    Escapes non-printable bytes and whitespace bytes except for ' '.
    """
    strlist = []
    for b in bs:
        c = chr(b)
        if curses.ascii.isprint(c) and (c==' ' or not curses.ascii.isspace(c)):
            strlist.append(c)
        else:
            #Take rightmost two hex characters
            strlist.append("\\x" + ("0" + hex(b)[2:])[-2:])
    return "".join(strlist)

class ForensicPath(object):
    def __init__(self, address):
        if isinstance(address, int):
            self._address = bytes(str(address), "ascii")
            self._parts = self._make_parts(address)
        elif isinstance(address, type(b"")):
            self._address = address
            self._parts = self._make_parts(address)
        elif isinstance(address,ForensicPath):
            #Clone-init
            self._address = address.get_address_byte_string()
            self._parts = copy.deepcopy(address.get_parts())
        else:
            raise ValueError("Unsure how to interpret as byte address: %r." % address)
        try:
            assert isinstance(self._parts[-1], int)
            assert self._parts[-1] >= 0
        except:
            sys.stderr.write("Error: Failed sanity checks on constructing object from forensic path: %r\n" % address)
            raise

    def _make_parts(self, address):
        """
        _parts is a tuple (hashable, where lists aren't) of path components from @address, either ASCII strings or ints.
        If this assumption's wrong...well, that'd be worth seeing.
        """
        tmpparts = self._address.split(b"-")
        retparts = []
        for (i, x) in enumerate(tmpparts):
            if x.isdigit():
                retparts.append(int(x))
            else:
                retparts.append(str(x, "ascii"))
        return tuple(retparts)

    def get_address_byte_string(self):
        return self._address

    def get_parts(self):
        return self._parts

    def split(self):
        """
        Returns a pair, (string prefix, int offset)
        """
        return ("-".join(map(str, self._parts[:-1])), self._parts[-1])

    def __repr__(self):
        return "ForensicPath(%r)" % self._address

    def __str__(self):
        return "ForensicPath(%r)" % self._address
        
    def __eq__(self, other):
        if type(other) in [int, type(b"")]:
            return self == ForensicPath(other)
        elif not isinstance(other, ForensicPath):
            return False
        return self._address == other.get_address_byte_string()

    def __lt__(self, other):
        if isinstance(other, int):
            return int(self._parts[0]) < other
        elif self == other:
            return False
        elif not isinstance(other, ForensicPath):
            raise ValueError("ForensicPath can't be compared to non-path, non-integer value.")

        myparts = self.get_parts()
        theirparts = other.get_parts()
        commonlen = min(len(myparts), len(theirparts))
        for i in range(commonlen):
            if myparts[i] != theirparts[i]:
                return myparts[i] < theirparts[i]

        #Consider the case: 20 < 20-GZIP-123
        #The first path is less than the second, because it is at the beginning of the region.
        #Also, in this case: 20 < 20-GZIP-0
        #We'll just chalk that up to lexicographic ordering.
        if myparts[commonlen-1] == theirparts[commonlen-1]:
            return len(myparts) < len(theirparts)
        raise ValueError("ForensicPath __lt__ results unexpected on inputs:\n\t%r\n\t%r" % (self, other))

    def __hash__(self):
        return self._address.__hash__()

class Feature(object):
    def __init__(self, address, feature, left_context, right_context, orig_line, ambiguously_parsed=None):
        self.feature = feature
        self.address = ForensicPath(address)
        self.left_context = left_context
        self.right_context = right_context
        self.orig_line = orig_line
        self.ambiguously_parsed = ambiguously_parsed
        self._featureclass = "Feature"
        #TODO Add a Set that shows all the lines that went into this gestalt feature.

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return \
          self.feature == other.feature and \
          self.address == other.address and \
          self.left_context == other.left_context and \
          self.right_context == other.right_context and \
          self.ambiguously_parsed == other.ambiguously_parsed

    def __str__(self):
        return self._str(False)
    
    def __repr__(self):
        """
        Eval-able string representation of the class.  For an explanation of why eval-able:
        <http://stackoverflow.com/a/2626364/1207160>
        """
        return "%s(%r,%r,%r,%r,%r,%r)" % (self._featureclass, self.address, self.feature, self.left_context, self.right_context, self.orig_line, self.ambiguously_parsed)
    
    def _str(self, encode):
        if encode:
            sf = self.feature.encode('string_escape')
            slc = self.left_context.encode('string_escape')
            src = self.right_context.encode('string_escape')
        else:
            sf = self.feature
            slc = self.left_context
            src = self.right_context
        return "<Feature at %s, '%s' | '%s' | '%s' >" % (str(self.address), slc, sf, src)

    def __lt__(self,other):
        """
        Only order Features by their addresses for now.
        """
        if not isinstance(other,Feature):
            raise TypeError("Cannot compare %s to Feature class." % type(other))
        return self.address < other.address

    def to_feature_file_line(self):
        """
        Converts class data to a string, in the format matching the input.
        TODO: Print in octal.  Do I need to resort a function like this? <http://bytes.com/topic/python/answers/743965-converting-octal-escaped-utf-8-a>
        """
        return "\t".join([
          self.address.get_address_byte_string().decode(),
          bytes_to_string(self.feature),
          bytes_to_string(b"".join([
            self.left_context,
            self.feature,
            self.right_context
          ]))
        ])

    def is_feature_beginning(self):
        """
        Meant to be over-ridden.
        """
        return False

class HTTPHeaderFeature(Feature):
    def __init__(self, *a, **kw):
        Feature.__init__(self, *a, **kw)
        self._featureclass = "HTTPHeaderFeature"
    
    def is_feature_beginning(self):
        """
        An HTTP header begins with either a Request line or a Response line.
        This matches the end of the request header, or the beginning of the response header.
        """
        if re.search(br"HTTP/\d.\d(\x0d\x0a|\015\012)", self.feature) \
          or re.search(br"HTTP/\d.\d \d\d\d ", self.feature):
            return True
        return False

"""
This global variable changes depending on the type of bulk_extractor features we're assembling.
"""
FeatureClass = Feature

def line_to_features(line, linesep=b"\n"):
    """Converts a line from a feature file to a list of Feature objects.  The list is due to possible ambiguities with a feature being found multiple times in its context window."""
    global FeatureClass
    #Remove only the feature file's newline character - don't use strip(), whitespace at the end of the line might be part of the feature.
    #The file's newline character _should_ show up as '\n', per PEP 278:
    #<http://stackoverflow.com/questions/454725/python-get-proper-line-ending>
    #(Via <http://stackoverflow.com/a/454731/1207160>)
    line_parts = line[:-len(linesep)].split(b"\t")
    line_decoded = line
    address = line_parts[0]
    feature = unescape_be_bytestring(line_parts[1])
    feature_in_context = unescape_be_bytestring(line_parts[2])

    feature_parts = feature_in_context.split(feature)
    if len(feature_parts) < 2:
        #This should be the feature; right of feature is in [2]
        raise Exception("Parsing error: Feature not found in own context.")
    #Quirk: The feature might be able to appear in the context window multiple times.
    #For instance, take this feature file line (with \t->\n):
    #  151342543
    #  From: %s
    #  \000From: %s (%s)\012\000From: %s\012\000Date: %s\012\000Repl
    #This line can be interpreted as these contexts:
    #  l:  \000
    #  r:  (%s)\012\000From: %s\012\000Date: %s\012\000Repl
    #Or
    #  l:  \000From: %s (%s)\012\000
    #  r:  \012\000Date: %s\012\000Repl
    #The first has an unreasonably long context, 30.  In some cases, this is sufficient to resolve the ambiguity.
    #However, it may be most correct to simply return multiple features, noting ambiguous parsing so later failures can be forgiven.
    retlist = []
    for candidate_break in range(len(feature_parts) - 1):
        left_context = feature.join(feature_parts[:candidate_break+1])
        right_context = feature.join(feature_parts[candidate_break+1:])
        retlist.append(FeatureClass(address, feature, left_context, right_context, line, (len(feature_parts)>2) ))
    return retlist

def distance_to_feature(left,right):
    """
    Returns distance from left's feature (not context) beginning to right's beginning, None if incomparable.
    (Distance in "a.b" from 'a' to 'b' is 2, from 'b' to 'a' is -2. A distance metric would be the absolute value of this function.)
    """
    if None in [left.address, right.address]:
        #Addresses are incomparable
        return None
    if left.address == right.address:
        return 0
    left_addr_parts = left.address.get_parts()
    right_addr_parts = right.address.get_parts()
    components_length = len(left_addr_parts)
    if components_length != len(right_addr_parts):
        #Addresses are incomparable
        return None
    #Iterate through components
    verified_matching = 0
    for i in range(components_length):
        if left_addr_parts[i] != right_addr_parts[i]:
            break
        verified_matching += 1
    if components_length-1 != verified_matching:
        #Addresses are incomparable, paths differ in middle
        return None
    try:
        left_offset = int(left_addr_parts[verified_matching])
        right_offset = int(right_addr_parts[verified_matching])
    except ValueError:
        sys.stderr.write("Error parsing paths, 0-based component %d: %s, %s.\n" % (verified_matching, left, right))
        raise
        
    return right_offset - left_offset

def distance_to_left_window_edges(left,right):
    """
    Returns distance from the left edge of "left's" context window to the left edge of "right's" context window.
    """
    d = distance_to_feature(left,right)
    if d is None:
        return None
    #Consider left.feature to be positioned at 0 in a new coordinate system
    left_winedge = 0 - len(left.left_context)
    right_winedge = d - len(right.left_context)
    #dprint("Window left-edges: %d, %d.  distance_to_feature: %d." % (left_winedge, right_winedge, d))
    return right_winedge - left_winedge

def overlap(left,right):
    """
    Two features overlap if their .feature or either context overlap in space; content is compared if addresses are comparable.
    """
    wd = distance_to_left_window_edges(left,right)
    if wd is None:
        return None
    if wd < 0:
        return overlap(right,left)
    left_window = b"".join([left.left_context, left.feature, left.right_context])
    return wd <= len(left_window)

def merge_features(left,right):
    """
    Type: (Feature, Feature) -> (None|Feature)
    Takes two Features, makes a single string including their contexts - the "Window."  If the left and right windows overlap, and the content matches, return a new feature. Else, return None.  The new contexts are whatever fall outside the .feature content.
    Assumes left's left context is to the right of right's left context; if vice versa, this is recursively called once.
    Returns None if distances are incomparable, the windows don't overlap, or the overlapping windows have mis-matched content.
    The resulting merged feature will only be considered ambiguously parsed if the input features are both ambiguously parsed.  Otherwise, any ambiguities are resolved by aligning with non-ambiguous features.
    If this function returns False, there is a parsing problem that should urgently be corrected.
    """
    global FeatureClass
    wd = distance_to_left_window_edges(left,right)
    #If left is actually to the right of right, then just keep this conceptually simple and recurse once.
    if wd is None:
        #Positions are incomparable.
        #dprint("merge_features: Positions are incomparable (%r, %r)" % (left.address, right.address))
        return None
    elif wd<0:
        #The right window starts before left; try the other way.
        return merge_features(right,left)
    
    if right.is_feature_beginning():
        return None

    left_window = b"".join([left.left_context, left.feature, left.right_context])
    right_window = b"".join([right.left_context, right.feature, right.right_context])

    if wd > len(left_window):
        #These don't overlap.
        #dprint("merge_features: Window distance > left window length (%r > %r)" % (wd, len(left_window)))
        return None

    #Determine comparison regions: The substrings of left_window and right_window that are supposed to match the other window
    comparison_right_coord = min(len(left_window), wd + len(right_window))
    left_comparison_region = left_window[wd : comparison_right_coord]
    right_comparison_region = right_window[ : comparison_right_coord-wd ]
    retval = left_comparison_region == right_comparison_region

    if retval == False and \
      None not in [left.ambiguously_parsed, right.ambiguously_parsed] and\
      max(left.ambiguously_parsed, right.ambiguously_parsed) == False:
        dprint("Warning: Overlapping feature windows do not have matching content! This really shouldn't happen!")
        dprint("\t" + "Features:")
        dprint("\t" + repr(left))
        dprint("\t" + repr(right))
        dprint("\t" + "Distances:")
        dprint("\t" + "distance_to_left_window_edges: " + str(wd))
        dprint("\t" + "distance_to_feature: " + str(distance_to_feature(left,right)))
        return None

    #How much of the new window is the new feature?
    #The new window is the left window, plus what comes after the right comparison region.
    new_window = left_window + right_window[len(right_comparison_region):]
    #Find the index of the leftmost of the original Feature.features
    new_left_context_end = min( len(left.left_context), wd + len(right.left_context) )
    new_right_context_start = max( len(left.left_context) + len(left.feature), wd + len(right.left_context) + len(right.feature) )

    #The address doesn't really change. The left feature is the leftmost of the features, so inherit its address.
    new_address = ForensicPath(left.address)

    #Create and verify new feature
    retval = FeatureClass(
      new_address,
      new_window[ new_left_context_end : new_right_context_start ],
      new_window[ : new_left_context_end ],
      new_window[ new_right_context_start : ],
      None,
      left.ambiguously_parsed and right.ambiguously_parsed
    )
    assert retval.feature[:len(left.feature)] == left.feature
    #assert retval.feature[-len(right.feature)] == right.feature TODO Little trickier, original right feature could've been embedded
    return retval

class MergingFeatureDatabase():
    """
    Not intended to be a subclass of dict().  Here, adding a new Feature object potentially destroys other Feature objects.
    """

    def __init__(self):
        #List of features, paired with their addresses for ease of sorting.
        self._featurelist = []

        #Key: Full forensic path
        #Value: List of all features parsed from that forensic path
        self._ambiguousdict = collections.defaultdict(list)
    
        #Key: Full forensic path
        #Value: Feature
        self._failedmergedict = collections.defaultdict(list)
    
        #List of Features, ambiguously parsed with no nearby features for merging.
        self._isolatedambiguousfeatures = []
    
    def add_feature(self, new_feature, attempt_ambiguous_resolution=False):
        """
        Stores new_feature at its address, merging with any features known to be nearby.
        Returns resulting merged feature, or just new_feature if there weren't any merges.
        Features that fail to merge, due to ambiguity or mismatch issues in overlapping content, are recorded.
        """
        if new_feature.ambiguously_parsed and not attempt_ambiguous_resolution:
            #Stash this feature for later.
            self._ambiguousdict[new_feature.address].append(new_feature)
            return new_feature
        #Maybe prime the list.
        if len(self._featurelist) == 0:
            self._featurelist.append((new_feature.address, new_feature))
            return new_feature
        #Try inserting at the end.
        last_feature = self._featurelist[-1][1]
        if new_feature > last_feature:
            #We have the right order.  Is the feature mergeable?
            merged = merge_features(last_feature, new_feature)
            if not merged is None:
                #Merge succeeded, pop old feature and replace with new feature.
                self._featurelist[-1] = (merged.address, merged)
                #Clear away any prior ambiguous inputs from this feature
                if merged.ambiguously_parsed == False:
                    if new_feature.address in self._ambiguousdict:
                        del self._ambiguousdict[new_feature.address]
                return merged
            #Feature couldn't merge. Was it because of non-proximity?
            if not overlap(new_feature, last_feature):
                self._featurelist.append((new_feature.address, new_feature))
                return new_feature
            #Was it because the new feature is flagged as a gestalt feature beginning?
            if new_feature.is_feature_beginning():
                self._featurelist.append((new_feature.address, new_feature))
                return new_feature
            #Was it because of ambiguity?
            if new_feature.ambiguously_parsed:
                #Stash ambiguous feature for later
                self._ambiguousdict[new_feature.address].append(new_feature)
                return new_feature

            sys.stderr.write("Warning: Failed to merge features:\n\t%r\n\t%r\n" % (last_feature, new_feature))
            self._failedmergedict[new_feature.address] = new_feature
            return new_feature

    def resolve_ambiguous_entries(self):
        """
        Try folding the ambiguous parsings into the rest of the feature database.
        """
        dprint("#Number of ambiguously-parsed Feature objects, before folding in: %d." % sum(len(x) for x in mfd._ambiguousdict.values()))
        for ambig_feature_address in sorted(self._ambiguousdict.keys()):
            #Each address supplied a list of maybe-features.
            ambiguous_features = self._ambiguousdict[ambig_feature_address]
            #successfully_merged_features: List of the ambiguous features, not the results of their merges.
            successfully_merged_features = []
            #isolated_features: Discarded if a feature at this adress merges.  (That would be a strange occurrence...))
            isolated_features = []
            features_nearest = []
            insertion_index = bisect.bisect_left(self._featurelist, (ambig_feature_address, None))
            if insertion_index > 0:
                features_nearest.append(self._featurelist[insertion_index-1][1])
            if insertion_index < len(self._featurelist)-1:
                features_nearest.append(self._featurelist[insertion_index][1])
            for af in ambiguous_features:
                features_near = [x for x in features_nearest if overlap(x, af)]
                if len(features_near) == 0:
                    #This feature has nothing nearby.  Store in a special, "Isolated" list.
                    isolated_features.append(af)
                else:
                    #Merge until a single feature remains, or quit trying this af if any merge fails.
                    merging_feature = af
                    for fn in features_near:
                        merging_feature = merge_features(merging_feature, af)
                        if merging_feature is None:
                            #Quit early, already failed.
                            break
                    if not merging_feature is None:
                        successfully_merged_features.append(fn)
            if len(successfully_merged_features) == 1:
                self.add_feature(successfully_merged_features[0], True)
                if ambig_feature_address in self._ambiguousdict:
                    del self._ambiguousdict[ambig_feature_address]
            else:
                #More than two mergings - unfortunately, still ambiguous.
                self._ambiguousdict[ambig_feature_address] = successfully_merged_features
                self._isolatedambiguousfeatures += isolated_features
        dprint("#Number of ambiguously-parsed Feature objects, after folding in: %d." % sum(len(x) for x in mfd._ambiguousdict.values()))
                    
    def __iter__(self):
        """
        Standard warning: Mutating this class while iterating voids your process's warranty.
        """
        for (address, feature) in self._featurelist:
            yield feature

    def isolated_ambiguous_feature_lines(self):
        """
        Returns just the originating lines that provided ambiguous parsings we couldn't resolve.
        """
        retlist = []
        for isoambigfeature in self._isolatedambiguousfeatures:
            retlist.append(isoambigfeature.orig_line)
        for ol in retlist:
            yield ol

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='reconstruct.py', description='Glom features from "bulk_extractor" output')
    parser.add_argument('-r', '--regress', action='store_true', dest='regress', help='Run unit tests and exit')
    args_regress = parser.parse_known_args()[0]

    #Unit tests
    if args_regress.regress:
        #To resolve any confusion with max (ab)use...
        assert max(True,False) == True
        #(Python 3 does not allow inequality comparisons between Booleans and None.)
        #assert max(True,None) == True
        #assert max(False,None) == False
        
        #In some places, hex() is called and then the first char is thrown away.  That's because it's a 0.
        assert hex(123) == '0x7b'
        
        assert bytes_to_string(b"\n") == "\\x0a"
        
        #Set the exemplar decoding calls
        #Frustrating issue almost resolved here: <http://stackoverflow.com/a/4020824/1207160>
        #TODO File encoding may be the way to go? Test in shell...
        #<http://stackoverflow.com/a/7373730/1207160>
        #testbytesstring: Example contents read from a binary file as Bulk Extractor would output; non-printable ASCII characters are encoded by octal escaping, so '\n' -> '\\012'
        testbytesstring = b'a\\012b'
        testbytesstring_unescaped = unescape_be_bytestring(testbytesstring)
        #dprint(testbytesstring_unescaped)
        assert len(testbytesstring_unescaped) == 3
        assert testbytesstring_unescaped == b'a\nb'
        
        fp1 = ForensicPath(b"123-ASDF-456")
        fp2 = ForensicPath(b"12-ASDF-3456")
        assert fp2 < fp1
        fp3 = ForensicPath(b"12")
        fp4 = ForensicPath(b"3")
        assert fp4 < fp3
        assert fp3 < fp2

        #Ensure single-quotes can be handled
        testbyteinjection = b"erAddr => 'localhost:\\nsmtp(25)\\');\\012\\012"
        testbyteinjection_unescaped = unescape_be_bytestring(testbyteinjection)
        assert testbyteinjection_unescaped == b"erAddr => 'localhost:\nsmtp(25)\\');\n\n"
        
        #Ensure non-ASCII input can be handled
        testspanish = b"\\000Proxy de HTTP (host:porta)\\000Op\xe7\xf5es do Term"
        testspanish_unescaped = unescape_be_bytestring(testspanish)
        #dprint(testspanish_unescaped)
        assert testspanish_unescaped == b"\x00Proxy de HTTP (host:porta)\x00Op\xe7\xf5es do Term"
        
        #Assume original line: ab__cd__ef, considering '__' as features with 2-byte context radius
        #Assume merging produces feature '__cd__'
        ftest1 = Feature(b'2', b'__', b'ab', b'cd', b'2\t__\tab__cd\n', False)
        ftest2 = Feature(b'6', b'__', b'cd', b'ef', b'6\t__\tcd__ef\n', False)
        assert distance_to_feature(ftest1, ftest1) == 0
        assert distance_to_feature(ftest1, ftest2) == 4
        assert distance_to_feature(ftest2, ftest1) == -4
        #dprint(str(distance_to_left_window_edges(ftest1, ftest2)))
        assert distance_to_left_window_edges(ftest1, ftest2) == 4
        #dprint(str(distance_to_left_window_edges(ftest2, ftest1)))
        assert distance_to_left_window_edges(ftest2, ftest1) == -4
        ftest12 = merge_features(ftest1, ftest2)
        assert not ftest12 is None
        #dprint(repr(ftest12))
        assert ftest12.address == ForensicPath(b'2')
        assert ftest12.feature == b'__cd__'
        assert ftest12.left_context == b'ab'
        assert ftest12.right_context == b'ef'
        #Now use a line of actual data - the feature came from a buggy extraction, but demonstrated an ambiguous-parsing issue since the feature appeared twice in the context window.
        ftest3 = Feature(b'151342528',b'From: %s (%s)',b'lx\x00Subject: %s\n\x00',b'\n\x00From: %s\n\x00Date',b'151342528\tFrom: %s (%s)\tlx\\000Subject: %s\\012\\000From: %s (%s)\\012\\000From: %s\\012\\000Date\n', False)
        ftest4 = Feature(b'151342543', b'From: %s', b'\000From: %s (%s)\012\000', b'\012\000Date: %s\012\000Repl', b'151342543\tFrom: %s\t\\000From: %s (%s)\\012\\000From: %s\\012\\000Date: %s\\012\\000Repl\n', True)
        assert distance_to_feature(ftest3, ftest4) == 15
        assert distance_to_feature(ftest4, ftest3) == -15
        #dprint(str(distance_to_left_window_edges(ftest3, ftest4)))
        assert distance_to_left_window_edges(ftest3, ftest4) == 15
        #dprint(str(distance_to_left_window_edges(ftest4, ftest3)))
        assert distance_to_left_window_edges(ftest4, ftest3) == -15
        ftest34 = merge_features(ftest3, ftest4)
        assert not ftest34 is None
        assert ftest34.feature == b'From: %s (%s)\n\x00From: %s'
        assert ftest34.left_context == b'lx\x00Subject: %s\n\x00'
        #dprint(repr(ftest34.right_context))
        assert ftest34.right_context == b'\n\x00Date: %s\n\x00Repl'
        exit(0)
    #End unit tests
    
    parser.add_argument('feature_file', type=argparse.FileType('rb'))
    args = parser.parse_args()
    
    #main()
    if args.feature_file.name.endswith("httpheader.txt"):
        FeatureClass = HTTPHeaderFeature
    mfd = MergingFeatureDatabase()
    ambig_line_tally = 0
    for line in args.feature_file:
        if line.startswith(b"#"):
            continue
        try:
            fs = line_to_features(line)
            if len(fs) == 0:
                sys.stderr.write("Warning:  Parsed line into no features:\n\t%r\n" % line)
                continue
            if fs[0].ambiguously_parsed:
                ambig_line_tally += 1
            for f in fs:
                mfd.add_feature(f)
        except:
            sys.stderr.write("Error:  Here is the line:\n\t%r\n" % line)
            raise
    mfd.resolve_ambiguous_entries()
    for f in mfd:
        print(f.to_feature_file_line())

    print("#(Ambiguously-parsed, isolated features)")
    for ol in mfd.isolated_ambiguous_feature_lines():
        print(ol)

    print("#Ambiguously-parsed features not merged: %d." % sum(len(x) for x in mfd._ambiguousdict.values()))
    print("#Unambiguously-parsed features that failed to merge: %d." % len(mfd._failedmergedict.keys()))
    print("#Ambiguously-parsed, isolated features: %d." % len([x for x in mfd.isolated_ambiguous_feature_lines()]))
    
    #print >>sys.stderr, "#Features that failed to merge:"
    #for addr in sorted(mfd._failedmergedict.keys()):
    #    print >>sys.stderr, mfd._failedmergedict[addr].to_feature_file_line()
