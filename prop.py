import itertools as it

"""
Some representations of formulae in propositional logic. It would be nice to
use something like PyEDA for this, but PyEDA supports only python 3 and
crpytominisat supports only python 2. Oh well. This stuff is easy enough, does
the job, and as a bonus, I suppose, I discovered the interesting encoding used
by `at_least`.

These amount to a crude and boorish implementation of propositional formulae
using the composite pattern.  It should be tested, but it isn't.
"""

def str_to_symbol(e):
    if isinstance(e, str):
        return Symbol(e)
    return e

class BoolExpr(object):
    def __init__(self, clauses):
        self.clauses = [str_to_symbol(c) for c in clauses]

    def subexpressions(self):
        for c in self.clauses:
            yield c

class Symbol(BoolExpr):
    def __init__(self, name):
        self.name = name

    def subexpressions(self):
        return

    def simplify(self):
        return self

    def cnf_clause(self, vars_to_ints):
        return vars_to_ints[self.name]

    def vars(self):
        return [self.name]

    def human_str(self):
        return self.name

    def __repr__(self):
        return self.name

class And(BoolExpr):
    def simplify(self):
        new_clauses = []
        for c in self.clauses:
            if isinstance(c, And):
                new_and = c.simplify()
                new_clauses.extend(new_and.subexpressions())
            else:
                new_clauses.append(c)
        return And(new_clauses)

    def vars(self):
        for c in self.clauses:
            for v in c.vars():
                yield v

    def cnf_clauses(self, vars_to_ints):
        for clause in self.clauses:
            yield clause.cnf_clause(vars_to_ints)

    def human_str(self):
        return "(" + " & ".join(c.human_str() for c in self.clauses) + ")"

    def __repr__(self):
        return "And({})".format(", ".join(str(s) for s in self.clauses))


class Or(BoolExpr):
    def vars(self):
        for c in self.clauses:
            for v in c.vars():
                yield v

    def simplify(self):
        new_clauses = []
        for c in self.clauses:
            if isinstance(c, Or):
                new_or = c.simplify()
                new_clauses.extend(new_or.subexpressions())
            else:
                new_clauses.append(c)
        return Or(new_clauses)

    def cnf_clause(self, vars_to_ints):
        def singlify(expr):
            if isinstance(expr, list):
                return expr[0]
            return expr
        return [singlify(d.cnf_clause(vars_to_ints)) for d in self.clauses]

    def human_str(self):
        return "(" + " | ".join(c.human_str() for c in self.clauses) + ")"

    def __repr__(self):
        return "Or({})".format(", ".join(str(s) for s in self.clauses))

class Not(BoolExpr):
    def __init__(self, clause):
        self.clause = str_to_symbol(clause)

    def vars(self):
        for v in self.clause.vars():
            yield v

    def subexpressions(self):
        yield self.clause

    def simplify(self):
        if isinstance(self.clause, Not):
            return self.clause.clause.simplify()
        return self

    def cnf_clause(self, vars_to_ints):
        return [-self.clause.cnf_clause(vars_to_ints)]

    def human_str(self):
        if isinstance(self.clause, Symbol):
            return "~{}".format(self.clause.human_str())
        return "~({})".format(self.clause_human_str())

    def __repr__(self):
        return "Not({})".format(str(self.clause))

def onehot(vars):
    """ exactly one of `vars` is true """
    conjs = []
    for v1, v2 in it.combinations(vars, 2):
        yield Or([Not(v1), Not(v2)])
    yield Or(vars)

def at_least(vars, n):
    """
    At least `n` of `vars` are true. This was new to me, but surely known. See
    http://seanbowman.me/blog/interesting-logic-identity/ for an explanation.
    Look up "cardinality constraints boolean satisfiability" or something like
    that for way more information and really cool encodings of statements like
    these. We're lucky here in that we can get away with this (simple and
    straightforward) encoding. It doesn't add any new variables. Since none of
    our other constraints do, either, all of our model variables have a clear,
    direct meaning in the game ("player X has card Y"). So, you know, we've got
    that going for us.
    """
    conj, n_vars = [], len(vars)
    for subvars in it.combinations(vars, n_vars - n + 1):
        yield Or(subvars)
