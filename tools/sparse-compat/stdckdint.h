/* SPDX-License-Identifier: CC0-1.0 */
/* Sparse-only C23 checked-integer compatibility for compiler resource headers. */
#ifndef RUSTBOX_SPARSE_STDCKDINT_H
#define RUSTBOX_SPARSE_STDCKDINT_H

#define __STDC_VERSION_STDCKDINT_H__ 202311L
#define ckd_add(result, left, right) \
  __builtin_add_overflow ((left), (right), (result))
#define ckd_sub(result, left, right) \
  __builtin_sub_overflow ((left), (right), (result))
#define ckd_mul(result, left, right) \
  __builtin_mul_overflow ((left), (right), (result))

#endif
