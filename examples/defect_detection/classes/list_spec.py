from micro_svm.types import *
from micro_svm.compiler import CompilerContext
from micro_svm.global_context import CONTEXT as spec


spec.register_structure(
    'std.Object', [], [
    ])

spec.register_structure(
    'std.List', ['std.Object'], [
        field('items', ref(array(ref(spec.structures['std.Object'])))),
    ])



def Object__init_(ctx: CompilerContext):
    _ = ctx.get_parameter('this')
    # ===

spec.register_function(
    name='<ctor>',
    parameters=[
        ('this', ref(spec.structures['std.Object'])),
    ],
    result=None,
    implementation=Object__init_,
    structure='std.Object',
    tags={ 'public', 'constructor', },
)



def Object_equals(ctx: CompilerContext):
    this   = ctx.get_parameter('this')
    other  = ctx.get_parameter('other')
    result = ctx.get_function_result()
    # ===
    ctx.write(result.w, this.r == other.r)

spec.register_function(
    name='equals',
    parameters=[
        ('this', ref(spec.structures['std.Object'])),
        ('other', ref(spec.structures['std.Object'])),
    ],
    result=boolean,
    implementation=Object_equals,
    structure='std.Object',
    tags={ 'public', },
)



def List__init_(ctx: CompilerContext):
    this = ctx.get_parameter('this')
    # ===
    ctx.call(('std.Object', '<ctor>'), [this.r], None, virtual=False)
    ctx.field_write(this.r, 'std.List', 'items', ctx.array_new(reference, ctx.const(0)))

spec.register_function(
    name='<ctor>',
    parameters=[
        ('this', ref(spec.structures['std.List'])),
    ],
    result=None,
    implementation=List__init_,
    structure='std.List',
    tags={ 'public', 'constructor', },
)



def List_equals(ctx: CompilerContext):
    this   = ctx.get_parameter('this')
    other  = ctx.get_parameter('other')
    result = ctx.get_function_result()
    items_this  = ctx.make_local_variable(reference)
    items_other = ctx.make_local_variable(reference)
    i           = ctx.make_local_variable(integer)
    count       = ctx.make_local_variable(integer)
    item_a      = ctx.make_local_variable(ref(spec.structures['std.Object']))
    item_b      = ctx.make_local_variable(ref(spec.structures['std.Object']))
    # ===
    ctx.branch(lambda: (
        ctx.instance_of(other.r, 'std.List')
    )).when_true(lambda: (
        ctx.write(items_this.w,  ctx.field_read(this.r,  'std.List', 'items')),
        ctx.write(items_other.w, ctx.field_read(other.r, 'std.List', 'items')),

        ctx.write(count.w, ctx.container_size(items_this.r)),
        ctx.write(
            result.w,
            count.r == ctx.container_size(items_other.r)
        ),

        ctx.write(i.w, ctx.const(0)),
        ctx.branch(lambda: (
            result.r & (i.r < count.r)
        )).when_true(lambda: (
            ctx.write(item_a.w, ctx.array_get(reference, items_this.r,  i.r)),
            ctx.write(item_b.w, ctx.array_get(reference, items_other.r, i.r)),

            ctx.assume(ctx.instance_of(item_a.r, 'std.Object') | (item_a.r == ctx.null_ref)),
            ctx.assume(ctx.instance_of(item_b.r, 'std.Object') | (item_b.r == ctx.null_ref)),

            ctx.write(result.w, ctx.call(('std.Object', 'equals'), [item_a.r, item_b.r], boolean)),
            ctx.write(i.w, i.r + ctx.const(1)),
        )).explore_while(),
    )).when_false(lambda: (
        ctx.write(result.w, ctx.const(False, boolean)),
    )).explore_if()

spec.register_function(
    name='equals',
    parameters=[
        ('this', ref(spec.structures['std.List'])),
        ('other', ref(spec.structures['std.Object'])),
    ],
    result=boolean,
    implementation=List_equals,
    structure='std.List',
    #tags={ 'public', },
)



if __name__ == "__main__":
    from micro_svm.serialization import save_context_to_file
    with open(f"./{__spec__.name.replace('.', '/')}.json", 'wt', encoding='utf8') as f:
        save_context_to_file(spec, f)
