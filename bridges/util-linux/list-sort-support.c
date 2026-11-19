/* SPDX-License-Identifier: GPL-2.0-or-later */
#define list_sort rustbox_canonical_list_sort
#include "list.h"
#undef list_sort

void list_sort(struct list_head *head,
	       int (*cmp)(struct list_head *a,
			  struct list_head *b,
			  void *data),
	       void *data)
{
	rustbox_canonical_list_sort(head, cmp, data);
}
