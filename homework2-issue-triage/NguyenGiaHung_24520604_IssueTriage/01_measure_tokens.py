import tiktoken


TEXT_EN = "A Roman aqueduct in Segovia carried water from mountain springs to the city."
TEXT_VI = "Cầu máng La Mã ở Segovia dẫn nước từ các con suối trên núi về thành phố."


def token_count(encoding_name, text):
    encoder = tiktoken.get_encoding(encoding_name)
    return len(encoder.encode(text))


def main():
    for encoding_name in ["cl100k_base", "o200k_base"]:
        count_en = token_count(encoding_name, TEXT_EN)
        count_vi = token_count(encoding_name, TEXT_VI)
        print(f"{encoding_name}: EN={count_en}, VI={count_vi}, ratio={count_vi / count_en:.2f}")


if __name__ == "__main__":
    main()
