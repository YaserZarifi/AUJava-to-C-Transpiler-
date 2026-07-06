# AUJava → C Transpiler — Project Report

> Placeholder — written incrementally across the project and finalized in Phase 12.

## Design assumptions (documented decisions)

The spec is ambiguous in a few places; here are the decisions we made and why.

1. **`println` accepts both `int` and `boolean`.** The language intro lists both,
   while the constraints section mentions only `int`. We follow the intro:
   `int` → `printf("%d\n", x)`, `boolean` → `printf(x ? "true\n" : "false\n")`.
   (Chosen by the team; can be narrowed to int-only if the TA requires it.)
2. **Upcast assignment is allowed.** A subclass instance may be assigned to a
   parent-typed variable/field/parameter (standard OOP). The reverse is rejected.
3. **Object equality (`==`, `!=`)** is allowed between two class types when one is
   a subclass of the other (or same class); it compiles to pointer comparison.
4. **Entry class** must contain *only* `main` (no other fields/methods), and there
   must be exactly one `public static void main(String[] args)` in the program.
5. **Fields** are zero/`false`/`NULL` initialized by the default constructor;
   field initializers are not part of the required feature set.
6. **Overriding** methods (bonus phase) must keep the same signature.
