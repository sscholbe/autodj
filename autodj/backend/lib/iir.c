// Adjust this for MSVC if necessary
#define EXPORT __attribute__((__visibility__("default")))

#define NUM_CHAN 2

struct sample_t
{
    float chan[NUM_CHAN];
};

EXPORT void iir(
    const float *coef_table,
    int coef_len,
    const int *coef_indices,
    const struct sample_t *input,
    struct sample_t *output,
    int num_samples)
{
    for (int i = coef_len; i < num_samples; i++)
    {
        struct sample_t tmp = {0};
        output[i] = tmp;
        const float *b = &coef_table[coef_indices[i] * coef_len * 2];
        const float *a = b + coef_len;
        for (int j = 0; j < coef_len; j++)
        {
            for (int c = 0; c < NUM_CHAN; c++)
            {
                tmp.chan[c] += b[j] * input[i - j].chan[c] - a[j] * output[i - j].chan[c];
            }
        }
        output[i] = tmp;
    }
}
