// A macro that emits a whole class, the way a project's own type-registration
// macro does.  The class is textually in the package but nobody authored it.
`define gen_wrapper_utils(base_t) \
    class base_t``_w; \
        function new(); \
        endfunction \
    endclass

package gen_pkg;

    /** A hand-written class: this one must always be documented. */
    class gen_real;
        /** Does the thing. */
        function void go();
        endfunction
    endclass

    `gen_wrapper_utils(alpha)
    `gen_wrapper_utils(beta)

endpackage
