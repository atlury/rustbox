// SPDX-License-Identifier: BSD-3-Clause OR GPL-2.0-only
#[forbid(unsafe_code)]
mod generator {
    use super::dictionary;
    use core::mem::MaybeUninit;

    const WEIGHTS: [usize; 6] = [0, 8, 6, 4, 3, 2];
    const fn weight(n: usize) -> usize {
        if n < WEIGHTS.len() {
            WEIGHTS[n]
        } else {
            WEIGHTS[WEIGHTS.len() - 1]
        }
    }
    const DISTRIBUTION_LEN: usize = {
        let mut total = 0;
        let mut i = 0;
        while i < dictionary::COUNT {
            total += weight(dictionary::LENGTHS[i] as usize);
            i += 1;
        }
        assert!(total > 0 && total <= 650);
        total
    };
    static DISTRIBUTION: [u8; DISTRIBUTION_LEN] = {
        let mut slots = [0; DISTRIBUTION_LEN];
        let mut end = 0;
        let mut i = 0;
        while i < dictionary::COUNT {
            let next = end + weight(dictionary::LENGTHS[i] as usize);
            while end < next {
                slots[end] = i as u8;
                end += 1;
            }
            i += 1;
        }
        slots
    };

    struct Writer<'a> {
        remaining: &'a mut [MaybeUninit<u8>],
        seed: u32,
    }

    impl Writer<'_> {
        fn random(&mut self, range: u32) -> u32 {
            self.seed = (self.seed.wrapping_mul(2654435761) ^ 2246822519).rotate_left(13);
            ((u64::from(self.seed) * u64::from(range)) >> 32) as u32
        }

        fn about(&mut self, range: u32) -> u32 {
            self.random(range) + self.random(range) + 1
        }

        fn word(&mut self, index: usize, separator: &[u8], capitalize: bool) {
            let word = dictionary::word(index);
            let remaining = core::mem::take(&mut self.remaining);
            let length = word.len() + separator.len();
            if length > remaining.len() {
                remaining.fill(MaybeUninit::new(b' '));
                if let Some((first, tail)) = remaining.split_first_mut() {
                    first.write(b'.');
                    if let Some(last) = tail.last_mut() {
                        last.write(b'\n');
                    }
                }
                return;
            }
            let (field, rest) = remaining.split_at_mut(length);
            for (dest, &byte) in field.iter_mut().zip(word.iter().chain(separator)) {
                dest.write(byte);
            }
            if capitalize {
                field[0].write(word[0].to_ascii_uppercase());
            }
            self.remaining = rest;
        }

        fn sentence(&mut self, count: u32) {
            let comma = self.about(9);
            let second_comma = comma + self.about(7);
            let end = if self.random(11) == 7 { b"? " } else { b". " };
            for i in 0..count {
                let pick = self.random(DISTRIBUTION_LEN as u32);
                let separator: &[u8] = if i + 1 == count {
                    end
                } else if i == comma || i == second_comma {
                    b", "
                } else {
                    b" "
                };
                self.word(usize::from(DISTRIBUTION[pick as usize]), separator, i == 0);
            }
        }
    }

    pub fn block(buffer: &mut [MaybeUninit<u8>], seed: u32, first: bool, fill: bool) -> usize {
        let size = buffer.len();
        let mut out = Writer {
            remaining: buffer,
            seed,
        };
        if first {
            for index in 0..19 {
                let separator: &[u8] = match index {
                    4 | 7 => b", ",
                    18 => b". ",
                    _ => b" ",
                };
                out.word(index, separator, index == 0);
            }
        }
        while !out.remaining.is_empty() {
            let sentences = out.about(7);
            for _ in 0..sentences {
                let words = out.about(11);
                out.sentence(words);
            }
            let remaining = core::mem::take(&mut out.remaining);
            let (newlines, rest) = remaining.split_at_mut(remaining.len().min(2));
            newlines.fill(MaybeUninit::new(b'\n'));
            out.remaining = rest;
            if !fill {
                break;
            }
        }
        size - out.remaining.len()
    }
}
