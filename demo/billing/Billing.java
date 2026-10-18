import java.security.*;
import javax.crypto.Cipher;

/** Deliberately legacy crypto in a files-only synthetic billing component. */
public final class Billing {
    public static void main(String[] args) throws Exception {
        KeyPairGenerator keys = KeyPairGenerator.getInstance("RSA");
        keys.initialize(2048);
        KeyPair pair = keys.generateKeyPair();
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(pair.getPrivate());
        Cipher legacy = Cipher.getInstance("AES/ECB/PKCS5Padding");
        MessageDigest etag = MessageDigest.getInstance("SHA-1");
        System.out.println(signer.getAlgorithm() + legacy.getAlgorithm() + etag.getAlgorithm());
    }
}
